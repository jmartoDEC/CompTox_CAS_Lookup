from shiny import App, reactive, render, req, ui
import requests
import pandas as pd

app_ui = ui.page_fluid(
    ui.input_text_area(id='textCAS', label='Input CAS Numbers:', value='Input comma separated CAS numbers.'),
    ui.input_action_button(id='updateCAS', label='Update Selections'),
    ui.input_radio_buttons(id='selectCAS', label='Select CAS:', choices=['50-00-0']),
    ui.input_action_button(id='run', label='Run'),
    ui.output_text_verbatim("out_text"),
    ui.output_data_frame("out_df"),
)

def server(input, output, session):
    @reactive.event(input.run)
    def txt():
        thiscas = input.selectCAS.get()
        thisch, fch, fstr = runCAS(str(thiscas))
        return [fch, fstr]
    @reactive.effect
    @reactive.event(input.updateCAS)
    def update_CAS_buttons():
        theseCAS = input.textCAS.get()
        theseCAS = theseCAS.replace(' ', '')
        splitCAS = theseCAS.split(',')
        ui.update_radio_buttons('selectCAS', choices=splitCAS)
    @render.text
    def out_text():
        return txt()[1]
    @render.data_frame
    def out_df():
        return render.DataTable(txt()[0])

app = App(app_ui, server)

def getDTX(cas):
    #Input a CAS number and this function will query the CompTox API to return its DTXSID
    headers = {
        'accept': 'application/json',
        #Personal API Key here, not for sharing
        'x-api-key': '676c177f-18f8-494c-9936-628f71930cd7',
    }
    queryurl = 'https://api-ccte.epa.gov/chemical/search/equal/%s' % str(cas)
    response = requests.get(queryurl, headers=headers)
    if response.status_code == 200:
        print("Successfully connected with CompTox API")
        out = response.json()
        print('Compound %s identified' % out[0]['preferredName'])
        return out[0]['dtxsid']
    elif response.status_code == 400:
        print("CAS Number Not Found in CompTox")
    elif response.status_code == 401:
        print("Invalid API Key.")
    elif response.status_code == 404:
        print("Compound not Found.")
    else:
        print("Invalid API Response: Status Code %s" % (str(response.status_code)))

def getChemInfo(DTXSID):
    #This function uses a DTXCID to output Preferred Name, Mass, and Density 
    #This is my personal API token for CompTox
    token = "676c177f-18f8-494c-9936-628f71930cd7"

    thisname, thismass, thisdensity, hazardout = None, None, None, None

    #Code adapted from https://curlconverter.com/ using https://api-ccte.epa.gov/docs/chemical.html 
    headers = {
        'accept': 'application/json',
        #Personal API Key here, not for sharing
        'x-api-key': '676c177f-18f8-494c-9936-628f71930cd7',
    }

    params = {
        'projection': 'chemicaldetailall',
    }
    queryurl = 'https://api-ccte.epa.gov/chemical/detail/search/by-dtxsid/%s' % (str(DTXSID))
    response = requests.get(queryurl, params=params, headers=headers)

    print('Grabbing chemical information for %s' % (str(DTXSID)))
    if response.status_code == 200:
        Chemical_Data = response.json()
        thisname, thismass, thisdensity = Chemical_Data['preferredName'], Chemical_Data['averageMass'], Chemical_Data['density']
        hazardqueryurl = 'https://api-ccte.epa.gov/hazard/human/search/by-dtxsid/%s' % (str(DTXSID))
        hazardresponse = requests.get(hazardqueryurl, params=params, headers=headers)
        if hazardresponse.status_code == 200:
            Hazard_Data = hazardresponse.json()
            hazardout = Hazard_Data
            if len(hazardout) > 0:
                print('Succesfully grabbed Hazard Data')
            else:
                print('Hazard Data succesfully queried. No Hazard Data found for %s.' % str(thisname))
        else:
            print('Hazard Data could not be grabbed')
    elif response.status_code == 401:
        print("Invalid API Key.")
    elif response.status_code == 404:
        print("Not Found.")
    else:
        print("Invalid API Response: Status Code %s" % (str(response.status_code)))
    return thisname, thismass, thisdensity, hazardout
    


#These are the comparison values for the three main exposure routs to determin high, moderate, or low toxicity
def toxinhalation(valuein):
    #Make sure input is in ppm
    if valuein <= 200:
        return 'High'
    if valuein >= 2000:
        return 'Low'
    else:
        return 'Moderate'

def toxoral(valuein):
    #Make sure input is in mg/kg
    if valuein <= 50:
        return 'High'
    if valuein >= 500:
        return 'Low'
    else:
        return 'Moderate'

def toxdermal(valuein):
    #Make sure input is in mg/kg
    if valuein <= 200:
        return 'High'
    if valuein >= 1000:
        return 'Low'
    else:
        return 'Moderate'

#I have created quick functions to convert units. mwin is the molecular weight, which can be grabbed when checking the compound (currently labelled as chemmass)
def convertmgltomgm3(valuein):
    thisvalue = valuein * 1000
    return thisvalue

def convertmgm3toppm(valuein, mwin):
    thisvalue = valuein * 24.45 / mwin
    return thisvalue

def convertmgltoppm(valuein, mwin):
    thismgm3 = convertmgltomgm3(valuein)
    thisppm = convertmgm3toppm(thismgm3, mwin)
    return thisppm

def designate_tox(row):
    if type(row['converted_tox'])==float:
        if row['exposureRoute'] == 'inhalation':
            return toxinhalation(row['converted_tox'])
        if row['exposureRoute'] == 'oral':
            return toxoral(row['converted_tox'])
        if row['exposureRoute'] == 'dermal':
            return toxdermal(row['converted_tox'])
    else:
        return 'Not evaluated'

#Here I convert toxicity numerical values to either ppm for inhalation route or mg/m3 for oral/dermal. I put 'Not evaluated' for other ones, but can expand this code in the future as this tool gets developed 
def convert_tox(row, chemmass):
    if (row['toxvalType'] == 'LC50') or (row['toxvalType'] == 'LD50'):
        if row['exposureRoute'] == 'inhalation':
            if row['toxvalUnits'] == 'mg/L':
                return convertmgltoppm(row['toxvalNumeric'], chemmass)
            if row['toxvalUnits'] == 'mg/m3':
                return convertmgm3toppm(row['toxvalNumeric'], chemmass)
            if row['toxvalUnits'] == 'ppm':
                return row['toxvalNumeric']
            else:
                return 'Not evaluated: incorrect units'
        if (row['exposureRoute'] == 'dermal') or (row['exposureRoute'] == 'oral'):
            if row['toxvalUnits'] == 'mg/L':
                return convertmgltomgm3(row['toxvalNumeric'])
            if row['toxvalUnits'] == 'mg/kg':
                return row['toxvalNumeric']
            else:
                return 'Not evaluated: incorrect units'
        else:
            return 'Not evaluated: incorrect exposure route'
    else:
        return 'Not evaluated: incorrect test type'
        
#Here I do the same as the convert_tox function, but I convert the units to generate that column
def convert_units(row):
    if (row['toxvalType'] == 'LC50') or (row['toxvalType'] == 'LD50'):
        if row['exposureRoute'] == 'inhalation':
            if row['toxvalUnits'] == 'mg/L':
                return 'ppm'
            if row['toxvalUnits'] == 'mg/m3':
                return 'ppm'
            if row['toxvalUnits'] == 'ppm':
                return row['toxvalUnits']
            else:
                return ''
        if (row['exposureRoute'] == 'dermal') or (row['exposureRoute'] == 'oral'):
            if row['toxvalUnits'] == 'mg/L':
                return 'mg/kg'
            if row['toxvalUnits'] == 'mg/kg':
                return row['toxvalUnits']
            else:
                return ''
        else:
            return ''
    else:
        return ''

#Create clean strings for the reported and converted doses
def gen_reported_dose(row):
    qualifier = ''
    thisqual = row['toxvalNumericQualifier']
    if (thisqual != '='):
        qualifier = '%s' % (str(thisqual))
    thisdose = '%s%s %s' % (str(qualifier), str(row['rounded_numeric']), str(row['toxvalUnits']))
    return thisdose

def gen_converted_dose(row):
    qualifier = ''
    thisqual = row['toxvalNumericQualifier']
    if (type((row['rounded_tox'])) == float) or (type((row['rounded_tox'])) == int):
        if (thisqual) != '=':
            qualifier = '%s' % (str(thisqual))
    thisdose = '%s%s %s' % (qualifier, row['rounded_tox'], row['converted_units'])
    return thisdose

#Ranking higher toxicity results above lower
rankdict_tox = {'High': 0, 'Moderate': 1, 'Low':2, 'Not evaluated': 3}
#Ranking if it was evaluated above if it wasn't
rankdict_eval = {'High': 0, 'Moderate': 0, 'Low':0, 'Not evaluated': 1}
#Ordering inhalation before oral before dermal studies
rankdict_exposure = {'inhalation': 0, 'oral': 1, 'dermal': 2}

#I made this function to either return the integer of the converted tox value or the rounded decimal (float) value to two decimal places for rows that had a converted toxicity value
def round_converted_tox(row):
    if type(row['converted_tox']) == float:
        if float(row['converted_tox']) == int(row['converted_tox']):
            return int(row['converted_tox'])
        else:
            return round(row['converted_tox'], 2)
    else:
        return row['converted_tox']

#Taking the lazy way out and making a function as above to do the same for the numeric toxicity value. Could combine these into one function that takes the column 
def round_numeric_tox(row):
    if (type(row['toxvalNumeric']) == float) or (type(row['toxvalNumeric']) == int):
        if float(row['toxvalNumeric']) == int(row['toxvalNumeric']):
            #When I don't return as a string it automatically adds two decimal places. Go figure.
            return str(int(row['toxvalNumeric']))
        else:
            return round(row['toxvalNumeric'], 2)
    else:
        return ''

def toxcolor(val):
    color = 'None'
    stylec = ''
    
    if val == 'High':
        color = '#FFC000'
        stylec = 'background-color: %s' % (str(color))
    if val == 'Moderate':
        color = '#FFFF00'
        stylec = 'background-color: %s' % (str(color))
    if val == 'Low':
        color = '#00B0F0'
        stylec = 'background-color: %s' % (str(color))
    
    return str(stylec)

def runconversions(inputCAS, chemname, chemmass, chemdensity, chemhazard): 
    ch1 = pd.DataFrame(chemhazard)
    ch1['converted_tox'] = ch1.apply(convert_tox, chemmass=chemmass, axis=1)
    ch1['converted_units'] = ch1.apply(convert_units, axis=1)
    ch1['tox_designation'] = ch1.apply(designate_tox, axis=1)
    ch1['yeseval_rank'] = ch1['tox_designation'].map(rankdict_eval)
    ch1['toxdes_rank'] = ch1['tox_designation'].map(rankdict_tox)
    ch1['exposureeval_rank'] = ch1['exposureRoute'].map(rankdict_exposure)
    ch1 = ch1.sort_values(by=['yeseval_rank', 'exposureeval_rank', 'toxvalType', 'toxdes_rank', 'speciesCommon'], ignore_index=True)
    ch1['rounded_tox'] = ch1.apply(round_converted_tox, axis=1)
    ch1['rounded_numeric'] = ch1.apply(round_numeric_tox, axis=1)
    ch1['reported_dose'] = ch1.apply(gen_reported_dose, axis=1)
    ch1['converted_dose'] = ch1.apply(gen_converted_dose, axis=1)
    ch1 = ch1.loc[ch1['source'] != 'TEST'] #For some reason, there is a TEST row for each compound
    ch2 = ch1[['toxvalType', 'reported_dose', 'converted_dose', 'exposureRoute', 'speciesCommon', 'tox_designation', 'year', 'source', 'subsource', 'supercategory', 'riskAssessmentClass', 'studyType', 'criticalEffect']].copy()
    ch_rename = ch2.rename(columns={'toxvalType': 'Test Type', 'reported_dose': 'Reported Dose Value', 'converted_dose': 'Converted Dose Value', 'exposureRoute': 'Exposure Route', 'speciesCommon': 'Species/Organism', 'tox_designation': 'Toxicity', 'year': 'Year', 'source': 'Source/Reference', 'subsource': 'Subsource', 'supercategory': 'Supercategory', 'riskAssessmentClass': 'Risk assessment', 'studyType': 'Study type', 'criticalEffect': 'Critical Effect'})
    ch_unformat = ch_rename
    totallen = len(ch2['tox_designation'])
    highlen = len(ch2.loc[ch2['tox_designation']=='High'])
    modlen = len(ch2.loc[ch2['tox_designation']=='Moderate'])
    lowlen = len(ch2.loc[ch2['tox_designation']=='Low'])
    sumlen = highlen + modlen + lowlen
    ch_mapped = ch_rename
    ch_mapped = ch_mapped.style.applymap(toxcolor)
    ch_mapped = ch_mapped.hide(axis="index")
    outputstr = ""
    outputstr = outputstr + ('CompTox Results for CAS Number %s' % str(inputCAS))
    outputstr = outputstr + ('\n%s (CAS# %s) has a reported mass of %s and density of %s' % (str(chemname), str(inputCAS), str(chemmass), str(chemdensity)))
    if chemdensity == None:
        outputstr = outputstr + ('\n\nNo density was found in CompTox. A density near 1 is assumed for inhalation result conversions.\n')
    elif (float(chemdensity) < 0.8) or (float(chemdensity) > 1.2):
        outputstr = outputstr + ('\nNOTE: the density %s is outside the 0.8-1.2g/cm^3 range. Converted inhalation results should be reviewed.\n' % str(chemdensity))
    outputstr = outputstr + ('\n%s studies were evaluated for toxicity results of %s total studies:\n   %s High Toxicity\n   %s Moderate Toxicity\n   %s Low Toxicity\n' % (str(sumlen), str(totallen), str(highlen), str(modlen), str(lowlen)))
    return ch_mapped, ch_unformat, outputstr

def runCAS(CASin):
    ch_m, ch_r, ch_s = None, None, None
    print('Evaluating %s' % str(CASin))
    thisDTX = getDTX(CASin)
    cname, cmass, cdensity, chazard = getChemInfo(thisDTX)
    if cname != None:
        if len(chazard) > 0:
            ch_m, ch_r, ch_s = runconversions(CASin, cname, cmass, cdensity, chazard)
    else:
        print('No results found')
    return ch_m, ch_r, ch_s

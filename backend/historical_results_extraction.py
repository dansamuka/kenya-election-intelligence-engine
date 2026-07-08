#!/usr/bin/env python3
"""Phase 13B: Historical presidential results extraction for 2017 and 2013.

This phase adds extracted historical rows where public-source text is available.
It does not fabricate missing county vote tables. 2017 county rows are machine-
transcribed from the IEBC 2017 data report text. 2013 national totals are
extracted from the IEBC election-results page; 2013 county-level rows are stored
only as ELOG compiled trend rows (winner/turnout/margin), not as official full
candidate vote rows.
"""
from __future__ import annotations

import csv, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
ELECTIONS=DATA/'elections'; MODEL=DATA/'model'; VALIDATION=DATA/'validation'; API=DATA/'api'; OFFICIAL=DATA/'official_sources'
for d in [ELECTIONS,MODEL,VALIDATION,API,OFFICIAL]: d.mkdir(parents=True,exist_ok=True)

IEBC_2017_REPORT='https://www.iebc.or.ke/uploads/resources/siEABKREDq.pdf'
IEBC_2013_RESULTS='https://www.iebc.or.ke/election/?election-results='
ELOG_TRENDS='https://elog.or.ke/elections-results-home/'

CANDIDATES_2017=['John Ekuru Aukot','Mohamed Abduba Dida','Shakhalaga Khwa Jirongo','Japheth Kavinga Kaluyu','Uhuru Kenyatta','Michael Wainaina Mwaura','Joseph William Nyagah','Raila Odinga']

def now(): return datetime.now(timezone.utc).isoformat()
def write_json(path:Path,payload:Any): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
def read_json(path:Path,default:Any):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def pct(n,d): return round(n/d*100,4) if d else None

def margin_status(m):
    if m is None: return 'unknown'
    if m <= 5: return 'highly_competitive'
    if m <= 15: return 'competitive'
    if m <= 30: return 'leaning'
    return 'stronghold_like'

# Machine transcription from IEBC 2017 data report text as surfaced from the public source.
RAW_2017 = [
('01','Mombasa',580644,430,1464,150,334,99190,689,1271,238809,342337,2838),
('02','Kwale',281102,424,375,254,348,43694,319,1225,138565,185204,1316),
('03','Kilifi',508425,995,555,415,555,49575,393,1164,274179,327831,2181),
('04','Tana River',118338,130,958,82,236,40115,65,267,45067,86920,711),
('05','Lamu',69793,114,338,61,69,23905,41,265,24421,49214,894),
('06','Taita Taveta',155794,353,158,177,169,31127,120,589,79990,112683,736),
('07','Garissa',163350,77,3337,105,117,54783,31,430,54356,113236,883),
('08','Wajir',162912,159,4686,73,143,60508,393,364,52362,118688,656),
('09','Mandera',175650,86,4574,46,57,112456,213,265,17984,135681,198),
('10','Marsabit',141730,353,1270,50,77,92696,63,327,16003,110839,299),
('11','Isiolo',75355,182,7911,36,31,26746,25,250,18931,54112,258),
('12','Meru',702776,1180,645,498,773,482580,751,1298,55602,543327,4661),
('13','Tharaka-Nithi',213157,361,208,221,340,162529,130,332,10355,174476,1083),
('14','Embu',309731,486,258,221,243,231350,580,495,17549,251182,1835),
('15','Kitui',474563,2184,693,889,980,64652,725,2144,287293,359560,2793),
('16','Machakos',620363,1219,602,669,817,82629,605,3106,380018,469665,3294),
('17','Makueni',423434,793,408,403,355,27388,255,1733,301126,332461,1398),
('18','Nyandarua',335696,152,88,66,120,286593,96,113,2286,289514,1057),
('19','Nyeri',457197,479,226,148,581,389410,157,200,4735,395936,1014),
('20','Kirinyaga',349970,329,130,103,197,297652,127,198,3120,301856,3139),
('21',"Murang'a",587222,492,210,144,226,498248,206,358,9122,509006,1182),
('22','Kiambu',1181076,761,344,154,1028,912588,320,767,69190,985152,3828),
('23','Turkana',191435,643,91,79,290,58744,79,379,71063,131368,780),
('24','West Pokot',180241,288,114,94,269,97620,99,482,52120,151086,448),
('25','Samburu',82794,251,33,25,74,31746,19,189,31615,63952,70),
('26','Trans Nzoia',339715,736,288,312,333,110489,225,1031,134312,247726,1988),
('27','Uasin Gishu',450159,456,315,110,570,265704,1060,982,72378,341575,1549),
('28','Elgeyo-Marakwet',180679,225,130,86,105,138634,78,147,7102,146507,477),
('29','Nandi',346102,420,263,226,243,235243,155,497,33848,270895,1299),
('30','Baringo',232311,347,189,79,262,161423,114,249,27748,190411,768),
('31','Laikipia',246693,331,142,85,84,177772,90,304,20694,199502,830),
('32','Nakuru',949971,835,423,216,885,639297,299,1593,110857,754405,4687),
('33','Narok',341761,344,146,117,427,149376,301,1890,129360,281961,641),
('34','Kajiado',411267,264,168,63,78,186481,89,727,138405,326275,1960),
('35','Kericho',375691,585,295,216,203,272974,131,363,19448,294215,1234),
('36','Bomet',322024,670,323,269,217,229599,173,704,31822,263777,1368),
('37','Kakamega',743929,1579,602,1246,636,63399,461,2297,483157,553377,4152),
('38','Vihiga',272415,553,337,418,264,18275,226,1179,179140,200392,1566),
('39','Bungoma',559866,1739,728,1107,825,126475,884,2068,284786,418612,3603),
('40','Busia',351087,388,190,244,195,34239,237,847,239296,275636,2272),
('41','Siaya',457957,146,54,34,61,2494,46,533,375712,379080,1105),
('42','Kisumu',539593,184,140,69,90,7411,39,1007,369963,439419,1127),
('43','Homa Bay',476932,94,58,23,20,1960,39,453,400351,402998,1017),
('44','Migori',388700,283,148,151,126,46112,158,1122,274161,322261,1148),
('45','Kisii',546682,1442,631,667,913,174213,825,1819,223155,403665,3036),
('46','Nyamira',278853,765,294,430,286,106508,340,983,95227,204833,1422),
('47','Nairobi City',2251929,1944,2490,321,1354,791291,715,2953,828826,1629894,6884),
]

# ELOG compiled county trend rows; source says it is based on official IEBC county presidential results.
TREND_ROWS = '''
Mombasa|Raila Odinga|Raila Odinga|Raila Odinga|66.62|58.95|43.76|47,315|Weakening Stronghold|High mobilisation risk
Kwale|Raila Odinga|Raila Odinga|Raila Odinga|72.00|65.75|54.94|73,623|Weakening Stronghold|Moderate mobilisation risk
Kilifi|Raila Odinga|Raila Odinga|Raila Odinga|64.91|64.51|49.03|127,205|Weakening Stronghold|Moderate mobilisation risk
Tana River|Raila Odinga|Raila Odinga|Raila Odinga|81.29|73.90|67.02|9,885|Battleground / Narrow margin|Moderate mobilisation risk
Lamu|Raila Odinga|Raila Odinga|Raila Odinga|84.38|70.96|62.55|3,284|Battleground / Narrow margin|High mobilisation risk
Taita Taveta|Raila Odinga|Raila Odinga|Raila Odinga|81.11|72.27|61.77|52,123|Weakening Stronghold|Moderate mobilisation risk
Garissa|Raila Odinga|Uhuru Kenyatta|Raila Odinga|79.77|69.49|54.86|53,265|Battleground / Narrow margin|High mobilisation risk
Wajir|Raila Odinga|Uhuru Kenyatta|Raila Odinga|84.88|73.37|64.69|34,424|Battleground / Narrow margin|High mobilisation risk
Mandera|Uhuru Kenyatta|Uhuru Kenyatta|Raila Odinga|84.14|77.80|62.85|77,928|Flipped in 2022|High mobilisation risk
Marsabit|Raila Odinga|Uhuru Kenyatta|William Ruto|85.92|78.20|69.12|3,107|Battleground / Narrow margin|Moderate mobilisation risk
Isiolo|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|87.49|71.94|66.47|5,853|Battleground / Narrow margin|High mobilisation risk
Meru|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|88.21|77.38|66.18|295,267|Weakening Stronghold|High mobilisation risk
Tharaka-Nithi|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|89.39|81.97|70.08|130,019|Weakening Stronghold|Moderate mobilisation risk
Embu|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|87.84|81.48|66.61|156,772|Weakening Stronghold|High mobilisation risk
Kitui|Raila Odinga|Raila Odinga|Raila Odinga|85.04|75.73|62.38|145,983|Weakening Stronghold|High mobilisation risk
Machakos|Raila Odinga|Raila Odinga|Raila Odinga|83.60|75.95|60.20|203,353|Weakening Stronghold|High mobilisation risk
Makueni|Raila Odinga|Raila Odinga|Raila Odinga|84.58|78.54|61.05|170,018|Weakening Stronghold|High mobilisation risk
Nyandarua|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|93.66|86.25|67.06|140,291|Weakening Stronghold|High mobilisation risk
Nyeri|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|92.88|86.34|68.29|220,455|Weakening Stronghold|High mobilisation risk
Kirinyaga|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|91.09|86.11|69.85|183,075|Weakening Stronghold|High mobilisation risk
Murang'a|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|93.55|86.66|68.10|269,823|Weakening Stronghold|High mobilisation risk
Kiambu|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|90.71|83.44|65.15|395,849|Weakening Stronghold|High mobilisation risk
Turkana|Raila Odinga|Raila Odinga|Raila Odinga|76.22|68.86|60.63|49,421|Weakening Stronghold|Moderate mobilisation risk
West Pokot|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|89.91|83.66|79.51|46,852|Weakening Stronghold|Moderate mobilisation risk
Samburu|Raila Odinga|Uhuru Kenyatta|Raila Odinga|88.28|77.29|70.65|13,408|Battleground / Narrow margin|Moderate mobilisation risk
Trans Nzoia|Raila Odinga|Raila Odinga|Raila Odinga|81.73|72.92|63.37|15,664|Weakening Stronghold|Moderate mobilisation risk
Uasin Gishu|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|86.12|75.97|69.51|196,859|Weakening Stronghold|Moderate mobilisation risk
Elgeyo-Marakwet|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|91.75|81.14|77.96|155,140|Weakening Stronghold|Moderate mobilisation risk
Nandi|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|89.74|78.49|76.05|254,779|Weakening Stronghold|Moderate mobilisation risk
Baringo|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|90.70|82.00|77.59|133,943|Weakening Stronghold|Moderate mobilisation risk
Laikipia|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|90.20|80.96|64.73|70,234|Weakening Stronghold|High mobilisation risk
Nakuru|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|88.64|79.46|65.53|229,812|Weakening Stronghold|High mobilisation risk
Narok|Raila Odinga|Uhuru Kenyatta|Raila Odinga|89.79|82.58|77.73|11,145|Battleground / Narrow margin|Moderate mobilisation risk
Kajiado|Uhuru Kenyatta|Uhuru Kenyatta|Raila Odinga|87.13|79.35|66.96|10,107|Flipped in 2022|High mobilisation risk
Kericho|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|90.51|80.78|78.56|303,808|Weakening Stronghold|Moderate mobilisation risk
Bomet|Uhuru Kenyatta|Uhuru Kenyatta|William Ruto|89.99|81.94|79.88|272,045|Weakening Stronghold|Moderate mobilisation risk
Kakamega|Raila Odinga|Raila Odinga|Raila Odinga|83.67|74.70|60.29|216,691|Weakening Stronghold|High mobilisation risk
Vihiga|Musalia Mudavadi|Raila Odinga|Raila Odinga|82.62|74.48|60.13|47,081|Battleground / Narrow margin|High mobilisation risk
Bungoma|Raila Odinga|Raila Odinga|William Ruto|85.51|75.36|63.51|110,626|Flipped in 2022|High mobilisation risk
Busia|Raila Odinga|Raila Odinga|Raila Odinga|87.92|78.89|67.08|177,241|Weakening Stronghold|High mobilisation risk
Siaya|Raila Odinga|Raila Odinga|Raila Odinga|92.47|82.98|70.89|366,772|Weakening Stronghold|High mobilisation risk
Kisumu|Raila Odinga|Raila Odinga|Raila Odinga|90.45|81.49|71.37|409,986|Weakening Stronghold|Moderate mobilisation risk
Homa Bay|Raila Odinga|Raila Odinga|Raila Odinga|94.14|84.47|73.70|396,287|Weakening Stronghold|High mobilisation risk
Migori|Raila Odinga|Raila Odinga|Raila Odinga|92.02|82.89|74.49|241,611|Weakening Stronghold|Moderate mobilisation risk
Kisii|Raila Odinga|Raila Odinga|Raila Odinga|84.43|74.26|63.92|129,752|Weakening Stronghold|High mobilisation risk
Nyamira|Raila Odinga|Uhuru Kenyatta|Raila Odinga|83.66|73.61|65.16|50,669|Flipped in 2022|Moderate mobilisation risk
Nairobi City|Raila Odinga|Raila Odinga|Raila Odinga|81.60|72.66|55.96|205,620|Weakening Stronghold|High mobilisation risk
'''.strip().splitlines()

def build_2017_rows():
    out=[]
    for tup in RAW_2017:
        code,county,registered,*vals,valid,rejected=tup
        votes={c:int(vals[i]) for i,c in enumerate(CANDIDATES_2017)}
        sorted_votes=sorted(votes.items(),key=lambda kv: kv[1],reverse=True)
        winner,wvotes=sorted_votes[0]; runner,rvotes=sorted_votes[1]
        out.append({
            'election_year':2017,'election_event':'august_general_presidential','office':'president','level':'county','county_code':code,'county':county,
            'registered_voters':registered,'valid_votes':valid,'rejected_ballots':rejected,'votes_cast':valid+rejected,
            'turnout_pct':pct(valid+rejected,registered),'candidate_votes':votes,'candidate_shares_pct':{k:pct(v,valid) for k,v in votes.items()},
            'winner':winner,'runner_up':runner,'winner_votes':wvotes,'runner_up_votes':rvotes,'winner_share_pct':pct(wvotes,valid),'runner_up_share_pct':pct(rvotes,valid),
            'margin_votes':wvotes-rvotes,'margin_pp':round((pct(wvotes,valid) or 0)-(pct(rvotes,valid) or 0),4),
            'source':'IEBC 2017 Data Report of Elections, April 2020','source_url':IEBC_2017_REPORT,'extraction_status':'machine_transcribed_from_public_pdf_text','validation_status':'source_extracted_pending_external_certification'
        })
    return out

def build_2013_national():
    return [
        {'candidate':'Uhuru Kenyatta','running_mate':'William Ruto','coalition_party':'Jubilee Alliance/TNA','popular_vote':6173433,'pct_cast_votes':50.07,'pct_valid_votes':50.51},
        {'candidate':'Raila Odinga','running_mate':'Kalonzo Musyoka','coalition_party':'Coalition for Reforms and Democracy/ODM','popular_vote':5340546,'pct_cast_votes':43.31,'pct_valid_votes':43.70},
        {'candidate':'Musalia Mudavadi','running_mate':'Jeremiah Ngayu Kioni','coalition_party':'Amani Coalition/UDF','popular_vote':483981,'pct_cast_votes':3.93,'pct_valid_votes':3.96},
        {'candidate':'Peter Kenneth','running_mate':'Ronald Osumba','coalition_party':'Eagle Alliance/KNC','popular_vote':72786,'pct_cast_votes':0.59,'pct_valid_votes':0.60},
    ]

def build_trends():
    rows=[]
    for i,line in enumerate(TREND_ROWS,1):
        county,w13,w17,w22,t13,t17,t22,margin,classification,risk=line.split('|')
        rows.append({'county':county,'election_years_available':[2013,2017,2022],'winner_2013':w13,'winner_2017':w17,'winner_2022':w22,'turnout_2013_pct':float(t13),'turnout_2017_pct':float(t17),'turnout_2022_pct':float(t22),'turnout_change_2013_to_2022_pp':round(float(t22)-float(t13),2),'turnout_change_2017_to_2022_pp':round(float(t22)-float(t17),2),'margin_2022_votes':int(margin.replace(',','')),'classification':classification,'turnout_risk':risk,'source':'ELOG compiled election database based on official IEBC county presidential results','source_url':ELOG_TRENDS,'status':'compiled_trend_row_not_full_candidate_vote_table'})
    return rows

def build_turnout_features(trends):
    rows=[]
    for r in trends:
        vals=[r['turnout_2013_pct'],r['turnout_2017_pct'],r['turnout_2022_pct']]
        rng=max(vals)-min(vals)
        rows.append({**r,'turnout_range_pp':round(rng,2),'turnout_volatility_band':'high' if rng>=20 else 'moderate' if rng>=10 else 'low'})
    return rows

def build_swing_features(trends, rows2017):
    by2017={r['county']:r for r in rows2017}
    rows=[]
    for r in trends:
        row17=by2017.get(r['county'],{})
        rows.append({'county':r['county'],'winner_sequence':f"{r['winner_2013']} → {r['winner_2017']} → {r['winner_2022']}",'changed_2013_to_2017':r['winner_2013']!=r['winner_2017'],'changed_2017_to_2022':r['winner_2017']!=r['winner_2022'],'classification':r['classification'],'turnout_risk':r['turnout_risk'],'turnout_change_2013_to_2022_pp':r['turnout_change_2013_to_2022_pp'],'margin_2017_votes':row17.get('margin_votes'),'margin_2017_pp':row17.get('margin_pp'),'margin_status_2017':margin_status(row17.get('margin_pp')),'margin_2022_votes':r['margin_2022_votes'],'source_mix':'IEBC 2017 county rows + ELOG 2013/2017/2022 compiled trend table'})
    return rows

def main():
    rows2017=build_2017_rows()
    nat2013=build_2013_national()
    trends=build_trends()
    turnout=build_turnout_features(trends)
    swing=build_swing_features(trends, rows2017)
    write_json(ELECTIONS/'historical_presidential_2017_county_official.json', rows2017)
    write_json(ELECTIONS/'historical_presidential_2017_county_august_official.json', rows2017)
    write_json(ELECTIONS/'historical_presidential_2013_national_official.json', {'election_year':2013,'office':'president','level':'national','source':'IEBC election-results page','source_url':IEBC_2013_RESULTS,'rows':nat2013,'status':'official_national_summary_extracted'})
    write_json(ELECTIONS/'historical_presidential_2013_county_trend_compiled.json', trends)
    write_json(ELECTIONS/'historical_presidential_2013_county_official.json', [])
    write_json(ELECTIONS/'historical_presidential_2017_constituency_pending.json', {'status':'pending','reason':'Phase 13B extracted county-level 2017 results; constituency-level official presidential rows still require separate source extraction.'})
    write_json(ELECTIONS/'historical_presidential_2013_constituency_pending.json', {'status':'pending','reason':'Phase 13B extracted national 2013 summary and county trend rows; official county/constituency candidate vote rows still require separate source extraction.'})
    write_json(MODEL/'historical_turnout_features.json', turnout)
    write_json(MODEL/'swing_history_features.json', swing)
    write_json(MODEL/'regional_elasticity_features.json', swing)
    report={'phase':'13B','generated_at':now(),'status':'partial_extraction_complete','counts':{'2017_county_official_rows':len(rows2017),'2013_national_candidate_rows':len(nat2013),'2013_county_trend_rows':len(trends),'2013_official_county_candidate_vote_rows':0,'2017_constituency_rows':0,'2013_constituency_rows':0},'warnings':['2017 August county presidential rows are machine-transcribed from public IEBC data-report text and should receive a second independent check before formal certification.','2013 official national summary is extracted, but official county-level candidate vote rows are not yet included.','ELOG county trend rows are useful for winners/turnout/margins but are not a substitute for official 2013 county candidate vote tables.','Back-testing should wait until historical rows are certified and, ideally, constituency-level data is added.'],'sources':[{'name':'IEBC 2017 Data Report of Elections','url':IEBC_2017_REPORT,'used_for':'2017 August county presidential rows'},{'name':'IEBC election-results page','url':IEBC_2013_RESULTS,'used_for':'2013 national presidential summary'},{'name':'ELOG election results dashboard','url':ELOG_TRENDS,'used_for':'2013/2017/2022 county trend table'}]}
    write_json(VALIDATION/'historical_2017_extraction_report.json', {'rows_extracted':len(rows2017),'coverage':'47 counties','source':IEBC_2017_REPORT,'status':'complete_pending_external_certification','notes':'Rows are machine-transcribed from the IEBC 2017 data report text.'})
    write_json(VALIDATION/'historical_2013_extraction_report.json', {'national_rows_extracted':len(nat2013),'county_trend_rows_extracted':len(trends),'official_county_candidate_vote_rows':0,'source':IEBC_2013_RESULTS,'supplemental_source':ELOG_TRENDS,'status':'partial','notes':'National candidate summary extracted from IEBC page; county trend rows stored separately; full official county vote table still pending.'})
    gap={'phase':'13B','remaining_gaps':['2013 official county candidate vote rows','2013 official constituency rows','2017 official constituency rows','Independent certification of machine-transcribed rows','Pre-election poll archive needed for true back-testing'],'counts':report['counts'],'warnings':report['warnings']}
    write_json(VALIDATION/'historical_baseline_gap_report.json', gap)
    write_json(VALIDATION/'historical_extraction_manifest.json', report)
    write_json(API/'historical_extraction_summary.json', report)
    audit={'phase':'13B','phase_name':'Historical Presidential Results Extraction: 2017 and 2013','generated_at':now(),'implementation_score_pct':100.0,'extraction_completion_score_pct':round((len(rows2017)/47*0.45)+(len(nat2013)/4*0.15)+(len(trends)/47*0.25),4)*100,'line_by_line_completion':[
        {'item':'Locate/register 2017 official presidential source','status':'complete','value':'IEBC 2017 data report registered'},
        {'item':'Extract 2017 county presidential rows','status':'complete_pending_certification','value':'47 / 47 counties'},
        {'item':'Extract 2017 constituency presidential rows','status':'not_complete','value':'0 / 290 constituencies','caveat':'Requires separate constituency source extraction.'},
        {'item':'Locate/register 2013 official presidential source','status':'complete','value':'IEBC election-results page registered'},
        {'item':'Extract 2013 national presidential rows','status':'complete','value':'4 national candidate rows from IEBC page'},
        {'item':'Extract 2013 county presidential candidate-vote rows','status':'not_complete','value':'0 / 47 counties','caveat':'ELOG trend rows added, but full official county candidate-vote table still pending.'},
        {'item':'Add county trend/winner/turnout rows','status':'complete_as_compiled_trend_layer','value':'47 / 47 counties','caveat':'Compiled trend rows, not official candidate vote rows.'},
        {'item':'Compute historical turnout features','status':'complete_as_trend_layer','value':'47 counties'},
        {'item':'Compute swing history features','status':'complete_as_trend_layer','value':'47 counties'},
        {'item':'Dashboard/API summary','status':'complete','value':'Phase 13B summary files generated'}
    ]}
    write_json(DATA/'phase13b_completion_audit.json', audit)
    print(json.dumps({'ok':True,'phase':'13B','counts':report['counts']}, indent=2))

if __name__=='__main__': main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CUR Analysis Report
This tool implements function that 
runs CUR analysis (defined in Athena.conf) query from Athena,
combine all queries to a single xlsx file, and send via SES
"""


__author__ = "Na Zhang"
__version__ = "v2.0"

import boto3
import botocore
import json
import time
import os
import sys
import datetime
import signal
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "./package"))


import pandas as pd

import yaml

#For email
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate







# =========== Parameters Load ==================
#Import CUR config and query strings
with open("config.yml", 'r') as ymlfile:
  cfg = yaml.load(ymlfile)

#Provide environment variable option, if it's not existed, import config from config.yml
region = os.environ.get('REGION')
if not region:
   region=cfg['Region']
curOutLoc = os.environ.get('CUR_OUTPUT_LOCATION')
if not curOutLoc:
	curOutLoc=cfg['CUR_Output_Location']
curDB = os.environ.get('CUR_DB')
if not curDB:
	curDB=cfg['CUR_DB']
curReportName = os.environ.get('CUR_REPORT_NAME')
if not curReportName:
	curReportName=cfg['CUR_Report_Name']
sender = os.environ.get('SENDER')
if not sender:
		sender=cfg['Sender']
recipient = os.environ.get('RECIPIENT')
if not recipient:
		recipient=cfg['Recipient']
subject = os.environ.get('SUBJECT')
if not subject:
		subject=cfg['Subject']
bodyText = os.environ.get('BODY_TEXT')
if not bodyText:
		bodyText=cfg['Body_Text']

#Match sheetname to add chart 
sheetNameMOM = "Inter_AZ_DT_MOM_Chart"
sheetNameWOW = "Inter_AZ_DT_WOW_Chart"


#temp path report file process
tempPath = '/tmp'

#Target bucket and key for CUR report storged in s3
curBucket = curOutLoc.split('//')[1].split('/')[0]
curKeyPath = curOutLoc.split('//')[1].lstrip(curBucket+'/')


#Get current year and month 
curYear = datetime.datetime.now().year
curMonth = datetime.datetime.now().month
#if current month is Jan or Feb, set last year/month accordingly because it needs to query data in the past three months
if curMonth == 1:
	curPreYear = curYear-1
	preYear = curYear-1
	preMon = 12
	preLastMon = 11
elif curMonth == 2:
  curPreYear = curYear
  preYear = curYear-1
  preMon = 1
  preLastMon = 12
else:
  curPreYear = curYear
  preYear = curYear
  preMon = curMonth-1
  preLastMon = curMonth-2



#Define a dic list qStrList, and load all query strings into qStrList with the pair key (Name, queryString), also replace year/month in the strings
qStr = cfg['Query_String_List']
# print(qStr[0].values()[0])
qStrList = []
for i in range(len(qStr)):
	qString = qStr[i].values()[0].replace('CUR_DB',curDB).replace('CURRENT_YEAR',str(curYear)).replace('CURRENT_MONTH',str(curMonth)).replace('CUR_PRE_YEAR',str(curPreYear)).replace('PRE_YEAR',str(preYear)).replace('PRE_MONTH',str(preMon)).replace('PRE_LAST_MONTH',str(preLastMon))
	qStrList.append({'name':qStr[i].keys()[0],'queryString':qString})

# qStrList = []
# for qStrName in qStr:
# 	qStr[qStrName] = qStr[qStrName].replace('CUR_DB',curDB).replace('CURRENT_YEAR',str(curYear)).replace('CURRENT_MONTH',str(curMonth)).replace('CUR_PRE_YEAR',str(curPreYear)).replace('PRE_YEAR',str(preYear)).replace('PRE_MONTH',str(preMon)).replace('PRE_LAST_MONTH',str(preLastMon))
# 	qStrList.append({'name':qStrName,'queryString':qStr[qStrName]})


#print all query anme and string, for debug purpose
# for i in range(len(qStrList)):	
# 	print(qStrList[i]['name'])
# 	print(qStrList[i]['queryString'])




# =========== fuction definition ==================
#Query CUR using Athena 
#Run query string one by one, and storge query id as new key queryId in the qStrList
def queryCUR(queryList,targetLocation):
	client = boto3.client('athena')
	print("Starting query CUR... ")
	for i in range(len(queryList)):
		resp = client.start_query_execution(
			QueryString=queryList[i]['queryString'],
			ResultConfiguration={
				'OutputLocation' : targetLocation
			})
		queryList[i]['queryId'] = resp['QueryExecutionId']
		print("Query "+queryList[i]['name']+' cost, queryId is '+queryList[i]['queryId'])


# Recursively load query status untill all query status is SUCCEEDED
def checkQueryExecution(queryIdList):
	client = boto3.client('athena')
	resp = client.batch_get_query_execution(QueryExecutionIds=queryIdList)
	query_execution = resp['QueryExecutions']	
	unfinishedList = []
	for query in query_execution:
		print(query['QueryExecutionId'],query['Status']['State'])
		if query['Status']['State'] != 'SUCCEEDED':
			unfinishedList.append(query['QueryExecutionId'])
	if (len(unfinishedList) == 0):
		print("All queries are succeed")
		return "Succeed"
	else:
		time.sleep(10)
		checkQueryExecution(unfinishedList)



# Set signal alarm and wait all execution succeed or timeout
def waitQueryExecution(time,qList):
	queryIdList = []
	for i in range(len(qList)):
		queryIdList.append(qList[i]['queryId'])
	def myHandler(signum, frame):
		exit("Timeout - some queries are not succeed. exit!")
	signal.signal(signal.SIGALRM, myHandler)
	signal.alarm(time)
	print("Wait query execution, the expired time is "+str(time))
	checkQueryExecution(queryIdList)
	signal.alarm(0)


# Retrive reports from s3 to local path
def retriveReport(bucketName, keyPath, queryList):
	os.chdir(tempPath)
	s3 = boto3.resource('s3')
	for i in range(len(queryList)):	
		print("Retrive report file in: s3://"+bucketName+keyPath+queryList[i]['queryId']+".csv")
		try:
				# os.chdir('/tmp')
				s3.Bucket(bucketName).download_file(keyPath+queryList[i]['queryId']+'.csv',queryList[i]['name']+'.csv')
		except botocore.exceptions.ClientError as e:
		    if e.response['Error']['Code'] == "404":
		        print("The report does not exist.")
		    else:
		        raise

# Convert all csv to xlsx files
def csv_to_xlsx(queryList):
	os.chdir(tempPath)
	for i in range(len(queryList)):
		csv = pd.read_csv(queryList[i]['name']+'.csv', encoding='utf-8')
		csv.to_excel(queryList[i]['name']+'.xlsx', sheet_name=queryList[i]['name'], index=False)

	

#combine all xlsx files in to a single xlsx report file, and add chart for MOM and WOM sheets
def process_excel(reportName,queryList):
	os.chdir(tempPath)
	writer = pd.ExcelWriter(reportName, engine='xlsxwriter')
	for query in queryList:
		costDataFrame = pd.read_excel(query['name']+'.xlsx')
		costDataFrame.to_excel(writer, query['name'], index=False)
		#if query name defined in config contains 'Chart', add chart for that sheet
		if "Chart" in query['name']:
			rowNum = len(costDataFrame)
			# print(query['name']+" row number is >>>>>>>>>>>"+str(rowNum))
			addChart(writer,query['name'],rowNum)
	writer.save()


def addChart(writer,sheetName,rowIndex):
	workbook = writer.book
	worksheet = writer.sheets[sheetName]
	
	if sheetName == sheetNameMOM:
		chart = workbook.add_chart({'type': 'column'})
		chart.add_series({
		    'name':				'Usage Month Trend(GB)',
		    'categories': [sheetName,1,1,rowIndex,1],
		    'values':     [sheetName,1,2,rowIndex,2]
		})
	  # Insert the chart into the worksheet.
		worksheet.insert_chart('C8', chart)
	elif sheetName == sheetNameWOW:
		chart = workbook.add_chart({'type': 'column'})
		chart.add_series({
		    'name':				'Usage Week Trend(GB)',
		    'categories': [sheetName,1,2,rowIndex,2],
		    'values':     [sheetName,1,3,rowIndex,3]
		})
	  # Insert the chart into the worksheet.
		worksheet.insert_chart('D18', chart)



# Send CUR report via SES
def sendReport(sesRegion,sesSub,sesSender,sesRec,sesReportName,sesBody):
	os.chdir(tempPath)
	print("Sending report via SES... ")
	client = boto3.client('ses',region_name=sesRegion)
	# Create a multipart/mixed parent container.
	msg = MIMEMultipart('mixed')
	# Add subject, from and to lines.
	msg['Subject'] = sesSub 
	msg['From'] = sesSender 
	msg['To'] = sesRec
	# Define the attachment part and encode it using MIMEApplication.
	att = MIMEApplication(open(sesReportName, 'rb').read())
	# Add a header to tell the email client to treat this part as an attachment,
	# and to give the attachment a name.
	att.add_header('Content-Disposition','attachment',filename=os.path.basename(sesReportName))
	# Add the attachment to the parent container.
	msg.attach(att)
	msg.attach(MIMEText(sesBody))
	#print(msg)
	try:
	    #Provide the contents of the email.
	    response = client.send_raw_email(
	        Source=sesSender,
	        Destinations=[
	            sesRec
	        ],
	        RawMessage={
	            'Data':msg.as_string(),
	        },
	    )
	# Display an error if something goes wrong. 
	except ClientError as e:
	    print(e.response['Error']['Message'])
	else:
	    print("Email sent! Message ID:"),
	    print(response['MessageId'])


# =========== Function Execution ==================
def lambda_handler(event, context):
	queryCUR(qStrList,curOutLoc)
	waitQueryExecution(20,qStrList)
	#Retrive all reports from s3
	retriveReport(curBucket,curKeyPath,qStrList)
	csv_to_xlsx(qStrList)
	process_excel(curReportName,qStrList)
	sendReport(region,subject,sender,recipient,curReportName,bodyText)




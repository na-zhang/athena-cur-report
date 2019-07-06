## CUR Automation Tool Guide
### Introduction
This automation tool helps users to generate required CUR analysis report from Athena and send it via mail periodically.
It’s a python script running in Lambda, triggered by CloudWatch event regularly (daily, weekly etc.) defined by users. The Lambda function queries CUR data (query strings are defined in config.yml file), pulls report files (*.csv) to local path, converts and combines them to a single xlsx report file, generates required graph, and sends the report to configured receipts via SES.
Current sample is generating data transfer report in varies dimensions including:    

    Inter_AZ_DT_MOM - Your month over month inter-AZ data transfer usage and change in the past three months      
    Inter_AZ_DT_WOW - Your week over weeek inter-AZ data transfer usage and change in the past three months     
    Inter_AZ_DT_Cur_Mon - Your current month inter-AZ data transfer split by reource ID   
    Inter_AZ_DT_Pre_Mon - Your previous month inter-AZ data transfer split by reource ID    
    Inter_AZ_DT_Pre_LastMon - The month before previous month inter-AZ data transfer split by reource ID    
  
You can also customize report by modifying query strings defined in config.yml to get your interested report. The main advantage of this tool is that you can get the report in ‘resource id’ and ‘hours’ granularity which cost explorer cannot provide(like top 5 S3 bucket usage).



### Prerequisites
1.	Enable CUR: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-reports-costusage.html 
2.	Configure dB and table in Athena to enable CUR queries over Athena:
https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/athena.html 
3.	Verify email addresses in SES to assure you own that mail address you send mails from: https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-email-addresses.html 


### Setup Steps
1.	Create a Lambda Role and grant permissions below:   
    * a. Athena query execution   
    * b. S3 read and write (resource path is target path for temp query results *.csv storage)    
    * c. SES access    
  
2.	Setup a Lambda function    
    * a.	Use Python 2.7 runtime    
    * b.	Handler name: curReport.lambda_handler    
    * c.	Config variables in either way: 1) Through config.yml OR 2) Set Environment Variables as follow: 
          
          REGION – SES region
          CUR_OUTPUT_LOCATION – S3 path where Athena query results are stored e.g. “S3://Your/Query/Results/Path/”     
          CUR_DB – CUR DB defined in Athena e.g. “my_athena_db.myathenareport”    
          SENDER – Your sender e-mail address (must be verified)    
          RECIPIENT – Your recipient e-mail addresses   
          SUBJECT – Your subject of cost report mail    
          BODY_TEXT – Your body text of cost report mail    
    * d. The tool has the follow dependencies which are included in ‘package’ sub folder: 
    
          numpy   
          Xlrd    
          Openpyxl    
          Xlsxwriter    
          pyyaml    
    * Regarding how to install python dependencies , refer the link: https://docs.aws.amazon.com/lambda/latest/dg/lambda-python-how-to-create-deployment-package.html#python-package-dependencies      
    * e.	Package config.yml, cost_report.py and package/ into a zip file, and upload it to Lambda    
    * f.	Use Lambda execution role defined in previous step    
  
3.	Create a schedule CloudWatch event with required invoke rate (e.g. daily, weekly), specify the lambda function created in previous step as target   

### Test
In Lambda, create any test event (because the function doesn’t need any event parameter or context input), and run test. You should receive a e-mail with cur-analysis-report file attached.


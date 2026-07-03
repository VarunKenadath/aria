
from pymongo import MongoClient
import os
import asyncio
from fastapi import FastAPI,HTTPException
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import date, time,datetime
from dateutil.relativedelta import relativedelta
@asynccontextmanager
async def lifespan(_: FastAPI):
   asyncio.create_task(clear_at_midnight())
   yield

app=FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
load_dotenv("sensitive_keys.env")


mongo_db_con=os.environ.get("mongo_db_con")
if not mongo_db_con:
    raise RuntimeError("mongo_db_con environment variable is not set")
client=MongoClient(mongo_db_con)
db=client["aria_v2"]

class SymptomPayload(BaseModel):
  symptom:str
  severity:str

class MedicationPayload(BaseModel):
  model_config = {"arbitrary_types_allowed": True}
  medication:str
  frequency:int
  dosage:str
  time_period:time
  time_now:time

@app.post("/symptom")
def post_symptom(payload: SymptomPayload):  
    try:
        symptoms = db["symptom"]
        result = symptoms.insert_one(payload.model_dump())
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

medications=db["medicine"]
medication_day_list=[]

async def clear_at_midnight():
   while True:
      now=datetime.now()
      seconds_until_midnight=(datetime.combine(now.date(),time.max)-now).total_seconds()
      await asyncio.sleep(seconds_until_midnight)
      medication_day_list.clear()


@app.get("/medicine")
def get_medication():
    try:
      results=list(medications.find({},{"_id":0}))
      return results
    except Exception as e :
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/medication_routine")
def medication_routine():
   try:
      medications_taken=get_medication()
      medication_day_list.clear()
      for m in medications_taken:
         try:
            if m.get('medication_intake_frequency')=='Daily':
               medication_day_list.append(m)

            elif m.get('medication_intake_frequency')=='Alternate days (Mon,Wed,Fri,Sun)':
               days_1=m.get('medication_intake_frequency').replace("Alternate days (","").replace(")","").split(",")
               if date.today().strftime("%a") in days_1:
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Alternate days (Tue,Thurs,Sat)':
               days_2=m.get('medication_intake_frequency').replace("Alternate days (","").replace(")","").split(",")
               if date.today().strftime("%a") in days_2:
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Fortnightly':
               date_prescribed=m.get('date_prescribed')
               if date_prescribed is None:
                  raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
               if date.today()==date_prescribed+datetime.timedelta(days=14):
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Monthly':
               date_prescribed=m.get('date_prescribed')
               if date_prescribed is None:
                  raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
               if date.today()==date_prescribed+relativedelta(months=1):
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Annually':
               date_prescribed=m.get('date_prescribed')
               if date_prescribed is None:
                  raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
               if date.today()==date_prescribed+relativedelta(years=1):
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Custom days':
               custom_days=m.get('custom_days')
               if custom_days is None:
                  raise HTTPException(status_code=422, detail=f"Missing custom_days for {m.get('medication_name')}")
               if date.today().strftime("%a") in custom_days:
                  medication_day_list.append(m)
               else:
                  continue

            elif m.get('medication_intake_frequency')=='Custom dates':
               if date.today()==m.get('custom_dates'):
                  medication_day_list.append(m)
               else:
                  continue

         except HTTPException:
            raise
         except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing {m.get('medication_name','unknown')}: {str(e)}")

      results=[]
      for n in medication_day_list:
         dosages=n.get('dosages')
         times=n.get('time')
         if dosages is None:
            raise HTTPException(status_code=422, detail=f"Missing dosages for {n.get('medication_name')}")
         if times is None:
            raise HTTPException(status_code=422, detail=f"Missing time for {n.get('medication_name')}")
         for a in range(0,len(dosages)):
            results.append(f"Today take {dosages[a]} of {n.get('medication_name')} at {times[a]}")
      if not results:
         raise HTTPException(status_code=404, detail="No medications scheduled for today")
      return results

   except HTTPException:
      raise
   except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
 


'''
   def alternate_days():
      query_alternate_days_1={'medication_intake_frequency':'Alternate days (Mon,Wed,Fri,Sun)'}
      query_alternate_days_2={'medication_intake_frequency':'Alternate days (Tue,Thurs,Sat)'}
      cursor_2=medications.find(query_alternate_days_1)
      cursor_3=medications.find(query_alternate_days_2)

      today=date.today().strftime("%a")
      for document in cursor_2:
         days_1=document.get('medication_intake_frequency').replace("Alternate days (","").replace(")","").split(",")
         if today in days_1:
            print(f"take {document.get('dosages')} of {document.get('medication_name')} at {document.get('time')}")

      for document in cursor_3:
         days_2=document.get('medication_intake_frequency').replace("Alternate days (","").replace(")","").split(",")
         if today in days_2:
            print(f"take {document.get('dosages')} of {document.get('medication_name')} at {document.get('time')}")
   alternate_days()

   def period_days():
      query_period_1={'medication_intake_frequency':'Fortnightly'}
      cursor_4=medications.find(query_period_1)
   
      query_period_2={'medication_intake_frequency':'Monthly'}
      cursor_5=medications.find(query_period_2)

      query_period_3={'medication_intake_frequency':'Annually'}
      cursor_6=medications.find(query_period_3)

      for document in cursor_4:
          d=document.get('date_prescribed')+datetime.timedelta(days=14)
          if d==date.today():
             print(f"take {document.get('dosages')} of {document.get('medication_name')} at {document.get('time')}")
             d=date.today()

      for document in cursor_5:
         d=document.date.today()+relativedelta(months=1)
         if d==date.today():
            print(f"take {document.get('dosages')} of {document.get('medication_name')} at {document.get('time')}")
            d=date.today()

      for document in cursor_6:
         d=document.date.today()+relativedelta(years=1)
         if d==date.today():
            print(f"take {document.get('dosages')} of {document.get('medication_name')} at {document.get('time')}")
            d=date.today()

   period_days()

   def custom_dates():
      query_period_1={'medication_intake_frequency':'Custom dates','medication_intake_frequency':'Custom days'}
      cursor=medications.find(query_period_1)
      for documents in cursor:
         if documents.get('medication_intake_frequency')=='Custom dates':
            if documents.date.today() in documents.get('custome_dates'):
               print(f"take {documents.get('dosages')} of {documents.get('medication_name')} at {documents.get('time')}")
            elif date.today().strftime("%a") in documents.get('custom_days'):
              print(f"take {documents.get('dosages')} of {documents.get('medication_name')} at {documents.get('time')}")   
   custom_dates()

query_daily={'medication_intake_frequency':'Daily'}
cursor=medications.find(query_daily)
'''
'''
#def remove_medication():
#   medicine.pop()

med_time_period=None
med_time_start=None
med_time_end=None
for document in cursor:
   med_time_period=document.get('medication_time_period')
   med_time_start=document.get('education_time_period_start')
   med_time_end=document.get('education_time_period_end')

if med_time_period=='Indefinite' or med_time_start<=date.today<=med_time_end:
  medication_routine()
#elif med_time_period!='Indefinite' and date.today not in (med_time_start,med_time_end):
#   remove_medication()

   
   
"""
   start_period=medications.medicine_time_period_start
   end_period=medications.medication_time_period_finish
   if datetime.today==start_period<=end_period:
      x=datetime.today
   else:
      return
   routine.append(x)
   if datetime.today().day==[medications.medication_intake_frequency]:
      y=datetime.today().day
   if datetime.today().day==[day in medications.custom_days]:
      z=datetime.today().day
   if datetime.today==medications.custom_days:
      t=datetime.today.day()
      
def test_db():
   query={'medication_time_period':'Indefinite'}
   cursor=medications.find(query)
   for document in cursor:
      print(document.get("medication_intake_frequency"))
"""   
'''
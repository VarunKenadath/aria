
from pymongo import MongoClient
import os 
from fastapi import FastAPI,HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

app=FastAPI()
load_dotenv("sensitive_keys.env")

mongo_db_con=os.environ.get("mongo_db_con")
if not mongo_db_con:
    raise RuntimeError("mongo_db_con environment variable is not set")
client=MongoClient(mongo_db_con)
db=client["aria_v2"]

class SymptomPayload(BaseModel):
  symptom_name:str
  severity:str

class MedicationPayload(BaseModel):
  medication:str
  dosage_frequency:str

@app.post("/symptom")
def post_symptom(payload: SymptomPayload):  
    try:
        symptoms = db["symptom"]
        result = symptoms.insert_one(payload.model_dump())
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/medicine")
def get_medication():
    try:
      medications=db["medicine"]
      results=list(medications.find({},{"_id":0}))
      med = results[0]
      return f"you are taking {med['medication_name']}\n{med['dosage_frequency']}"
    except Exception as e :
        raise HTTPException(status_code=500, detail=str(e))
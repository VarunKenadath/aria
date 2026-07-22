
from pymongo import MongoClient
import os
import asyncio
import re
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import date, time, datetime, timedelta
from dateutil.relativedelta import relativedelta

@asynccontextmanager
async def lifespan(_: FastAPI):
    asyncio.create_task(clear_at_midnight())
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
load_dotenv("sensitive_keys.env")

mongo_db_con = os.environ.get("mongo_db_con")
if not mongo_db_con:
    raise RuntimeError("mongo_db_con environment variable is not set")
client = MongoClient(mongo_db_con)
db = client["aria_v2"]


class SymptomPayload(BaseModel):
    symptom: str
    severity: str


class MedicationPayload(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    medication: str
    frequency: int
    dosage: str
    time_period: time
    time_now: time


# NEW: response model so the agent (and OpenAPI schema) has a named field to bind to
class MedicationRoutineResponse(BaseModel):
    routine: list[str]


@app.post("/symptom")
def post_symptom(payload: SymptomPayload):
    try:
        symptoms = db["symptom"]
        result = symptoms.insert_one(payload.model_dump())
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


medications = db["medicine"]
medication_day_list = []


async def clear_at_midnight():
    while True:
        now = datetime.now()
        seconds_until_midnight = (datetime.combine(now.date(), time.max) - now).total_seconds()
        await asyncio.sleep(seconds_until_midnight)
        medication_day_list.clear()


@app.get("/medicine")
def get_medication():
    try:
        results = list(medications.find({}, {"_id": 0}))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_times(times_field):
    if isinstance(times_field, list):
        return [t[:5] for t in times_field]
    if isinstance(times_field, str):
        matches = re.findall(r'datetime\.time\((\d+),\s*(\d+)\)', times_field)
        if matches:
            return [f"{int(h):02d}:{int(m):02d}" for h, m in matches]
        matches = re.findall(r'(\d{2}:\d{2})', times_field)
        if matches:
            return matches
    return []


@app.get("/medication_routine", response_model=MedicationRoutineResponse)
def medication_routine():
    try:
        medications_taken = get_medication()
        medication_day_list.clear()
        for m in medications_taken:
            try:
                if m.get('medication_intake_frequency') == 'Daily':
                    medication_day_list.append(m)

                elif m.get('medication_intake_frequency') == 'Alternate days (Mon,Wed,Fri,Sun)':
                    days_1 = m.get('medication_intake_frequency').replace("Alternate days (", "").replace(")", "").split(",")
                    if date.today().strftime("%a") in days_1:
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Alternate days (Tue,Thurs,Sat)':
                    days_2 = m.get('medication_intake_frequency').replace("Alternate days (", "").replace(")", "").split(",")
                    if date.today().strftime("%a") in days_2:
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Fortnightly':
                    date_prescribed = m.get('date_prescribed')
                    if date_prescribed is None:
                        raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
                    if date.today() == date_prescribed + timedelta(days=14):
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Monthly':
                    date_prescribed = m.get('date_prescribed')
                    if date_prescribed is None:
                        raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
                    if date.today() == date_prescribed + relativedelta(months=1):
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Annually':
                    date_prescribed = m.get('date_prescribed')
                    if date_prescribed is None:
                        raise HTTPException(status_code=422, detail=f"Missing date_prescribed for {m.get('medication_name')}")
                    if date.today() == date_prescribed + relativedelta(years=1):
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Custom days':
                    custom_days = m.get('custom_days')
                    if custom_days is None:
                        raise HTTPException(status_code=422, detail=f"Missing custom_days for {m.get('medication_name')}")
                    if date.today().strftime("%a") in custom_days:
                        medication_day_list.append(m)
                    else:
                        continue

                elif m.get('medication_intake_frequency') == 'Custom dates':
                    if date.today() == m.get('custom_dates'):
                        medication_day_list.append(m)
                    else:
                        continue

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error processing {m.get('medication_name', 'unknown')}: {str(e)}")

        results = []
        for n in medication_day_list:
            dosages = n.get('dosages')
            times = parse_times(n.get('time'))
            if dosages is None:
                raise HTTPException(status_code=422, detail=f"Missing dosages for {n.get('medication_name')}")
            if not times:
                raise HTTPException(status_code=422, detail=f"Missing time for {n.get('medication_name')}")
            for a in range(0, len(dosages)):
                results.append(f"Today take {dosages[a]} of {n.get('medication_name')} at {times[a]}")

        # CHANGED: return empty routine with 200 instead of raising 404
        return {"routine": results}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
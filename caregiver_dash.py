import streamlit as st
import pymongo
from datetime import date, time

st.set_page_config(page_title="Aria Caregiver Dashboard", layout="wide")

st.markdown("""
<style>
    [data-testid="stForm"] {
        border: 1px solid #d0d7de;
        border-radius: 12px;
        padding: 24px;
        background-color: #f9fafb;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }
    .symptom-card {
        border: 1px solid #ffd6a5;
        border-radius: 10px;
        padding: 14px 20px;
        margin: 8px 0;
        background-color: #fff8f0;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        font-size: 0.97rem;
    }
    .symptom-card b { color: #b45309; }
    .cancel-box {
        border: 1px solid #fecaca;
        border-radius: 12px;
        padding: 24px;
        background-color: #fff5f5;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }
</style>
""", unsafe_allow_html=True)

st.title("Aria Caregiver Dashboard")
st.divider()

@st.cache_resource
def init_connection():
    return pymongo.MongoClient(st.secrets["mongo_db_con"])

client = init_connection()
db = client['aria_v2']
medicine_collection=db['medicine']

def get_symptoms():# getting symptoms from db
    items = db.symptom.find()
    return list(items)

def prescribe_medication(): # doctors prescribes medication and sets different guardrails for the medication
    medication_name = st.text_input("Medication Name")
    frequency = st.number_input("Enter Frequency (doses per day)", min_value=1, step=1)
    medication_time_period = st.selectbox("Choose a time period for medication", ("Indefinite", "Custom"))
    medication_time_period_start = None
    medication_time_period_finish = None
    if medication_time_period == 'Custom':# code to allow doctors to select customized time periods for medicine intake
        medication_time_period_start = st.date_input("Start date", value=date.today())
        medication_time_period_finish = st.date_input("Finish date", value=date.today())
    medication_intake_frequency = st.selectbox("Choose frequency for intake of medication", ("Daily", "Alternate days (Mon,Wed,Fri,Sun)", "Alternate days (Tue,Thurs,Sat)", "Fortnightly", "Monthly", "Annually", "Custom days", "Custom dates"))
    custom_days = None
    custom_dates=None
    if medication_intake_frequency == 'Custom days':
        custom_days = st.multiselect("Select days", ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
    elif medication_intake_frequency == 'Custom dates':# setting customized dates for consumption of medicine
        if 'custom_dates_list' not in st.session_state:
            st.session_state.custom_dates_list = []
        date_to_add = st.date_input("Pick a date to add", value=date.today(), key="date_picker")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Add Date"):
                if date_to_add not in st.session_state.custom_dates_list:
                    st.session_state.custom_dates_list.append(date_to_add)
        with col2:
            if st.button("Clear All Dates"):
                st.session_state.custom_dates_list = []
        if st.session_state.custom_dates_list:
            st.write("Selected dates:", sorted(st.session_state.custom_dates_list))
        custom_dates = [str(d) for d in st.session_state.custom_dates_list]
    with st.form("prescribe_form", clear_on_submit=True):
        dosages = []   
        times = []
        for i in range(int(frequency)):
            dosages.append(st.text_input(f"Dosage {i + 1}"))
        for i in range(int(frequency)):
            times.append(st.time_input(f"Time {i+1}"))
        submit_button = st.form_submit_button("Prescribe")
        if submit_button:
            document = {
                "medication_name": medication_name,
                "frequency": int(frequency),
                "dosages": dosages,
                "time": [str(t) for t in times],
                "date_prescribed":date.today(),     
                "medication_time_period": medication_time_period,
                "medication_time_period_start": str(medication_time_period_start) if medication_time_period_start else None,
                "medication_time_period_finish": str(medication_time_period_finish) if medication_time_period_finish else None,
                "medication_intake_frequency": medication_intake_frequency,
                "custom_days": custom_days,
                "custom_dates":custom_dates
            }
            st.write(f"Prescribed {medication_name} at {int(frequency)} dose(s) per day")
            medicine_collection.insert_one(document)

def cancel_medication():
    st.markdown('<div class="cancel-box">', unsafe_allow_html=True)
    medications = list(medicine_collection.find({}, {"_id": 1, "medication_name": 1}))
    if not medications:
        st.info("No medications found.")
    else:
        options = {m["medication_name"]: m["_id"] for m in medications}
        selected = st.selectbox("Select medication to cancel", list(options.keys()))
        if st.button("Cancel Medication"):
            medicine_collection.delete_one({"_id": options[selected]})
            st.success(f"{selected} has been removed.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Prescribe Medication", "Cancel Medication"])
with tab1:
    prescribe_medication()
with tab2:
    cancel_medication()

st.divider()
st.subheader("Patient Symptoms")
items = get_symptoms()
if not items:
    st.info("No symptoms reported.")
else:
    for item in items:
        st.markdown(f"""
        <div class="symptom-card">
            <b>Symptom:</b> {item['symptom']} &nbsp;|&nbsp; <b>Severity:</b> {item['severity']}
        </div>
        """, unsafe_allow_html=True)
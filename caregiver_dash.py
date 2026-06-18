import streamlit as st
import pymongo

@st.cache_resource
def init_connection():
    return pymongo.MongoClient(st.secrets["mongo_db_con"])

client = init_connection()
db = client['aria_v2']
medicine_collection=db['medicine']

def get_symptoms():
    items = db.symptom.find()
    return list(items)

def prescribe_medication():
    with st.form("prescribe_form",clear_on_submit=True):
        medication_name = st.text_input("Medication Name")
        dosage_frequency = st.text_input("Dosage and frequency")
        submit_button = st.form_submit_button("Prescribe")
        if submit_button:
            document={
                "medication_name":medication_name,
                "dosage_frequency":dosage_frequency
            }
            st.write(f"Prescribed {medication_name} for {dosage_frequency}")
            medicine_collection.insert_one(document)
        

prescribe_medication()
items = get_symptoms()

for item in items:
    st.write(f"Patient is experiencing {item['symptom']} at a severity of {item['severity']}")

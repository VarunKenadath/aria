"""
Unit tests for caregiver_dash.py business logic.

Streamlit's module-level calls (st.set_page_config, init_connection, tab rendering)
are fully mocked so the functions can be imported and tested in isolation.
"""
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date


# ---------------------------------------------------------------------------
# Bootstrap: stub out streamlit and pymongo BEFORE the module is imported
# ---------------------------------------------------------------------------

def _make_st_stub():
    st = MagicMock()
    # session_state must behave like a real dict
    st.session_state = {}
    # secrets must support key access
    st.secrets = {"mongo_db_con": "mongodb://fake"}
    # cache_resource returns the decorated function unchanged
    st.cache_resource = lambda fn: fn
    # tab1, tab2 = st.tabs(...) and col1, col2 = st.columns(...) unpack
    # the return value; a bare MagicMock iterates as empty, so give
    # them concrete tuples of (context-manager-capable) MagicMocks.
    st.tabs.return_value = (MagicMock(), MagicMock())
    st.columns.return_value = (MagicMock(), MagicMock())
    return st


@pytest.fixture(scope="module", autouse=True)
def stub_imports():
    """Inject stubs before caregiver_dash is imported."""
    st_stub = _make_st_stub()
    pymongo_stub = MagicMock()

    sys.modules["streamlit"] = st_stub
    sys.modules["pymongo"] = pymongo_stub

    yield st_stub, pymongo_stub

    # Tear down so other test sessions start clean
    del sys.modules["streamlit"]
    del sys.modules["pymongo"]
    if "caregiver_dash" in sys.modules:
        del sys.modules["caregiver_dash"]


@pytest.fixture(scope="module")
def dash(stub_imports):
    """Import caregiver_dash once with all stubs in place."""
    st_stub, pymongo_stub = stub_imports

    # init_connection() is called at module level; give it a fake client
    fake_client = MagicMock()
    pymongo_stub.MongoClient.return_value = fake_client

    import caregiver_dash as cd
    return cd


# ---------------------------------------------------------------------------
# get_symptoms
# ---------------------------------------------------------------------------

class TestGetSymptoms:
    def test_returns_list_of_documents(self, dash):
        docs = [{"symptom": "headache", "severity": "mild"},
                {"symptom": "nausea",   "severity": "severe"}]
        dash.db.symptom.find.return_value = iter(docs)
        result = dash.get_symptoms()
        assert result == docs

    def test_returns_empty_list_when_no_symptoms(self, dash):
        dash.db.symptom.find.return_value = iter([])
        result = dash.get_symptoms()
        assert result == []

    def test_calls_find_with_no_filter(self, dash):
        dash.db.symptom.find.return_value = iter([])
        dash.get_symptoms()
        dash.db.symptom.find.assert_called()


# ---------------------------------------------------------------------------
# prescribe_medication — document construction & DB insert
# ---------------------------------------------------------------------------

class TestPrescribeMedication:
    """
    prescribe_medication() is UI-heavy; we drive it by pre-configuring
    what every st.* call returns, then assert on the MongoDB insert.
    """

    def _setup_st(self, st_stub, *, name, frequency, time_period,
                  intake_freq, dosages, times,
                  custom_days=None, custom_dates=None,
                  submit=True):
        st_stub.text_input.return_value = name
        st_stub.number_input.return_value = frequency
        st_stub.selectbox.side_effect = [time_period, intake_freq]
        st_stub.time_input.side_effect = times
        # form context manager
        form_cm = MagicMock()
        form_cm.__enter__ = MagicMock(return_value=form_cm)
        form_cm.__exit__ = MagicMock(return_value=False)
        st_stub.form.return_value = form_cm
        st_stub.form_submit_button.return_value = submit
        if custom_days:
            st_stub.multiselect.return_value = custom_days
        if custom_dates:
            st_stub.session_state["custom_dates_list"] = custom_dates

    def test_insert_called_on_submit(self, dash, stub_imports):
        st_stub, _ = stub_imports
        self._setup_st(
            st_stub,
            name="Aspirin",
            frequency=1,
            time_period="Indefinite",
            intake_freq="Daily",
            dosages=["100mg"],
            times=[MagicMock(__str__=lambda s: "08:00:00")],
            submit=True,
        )
        dash.medicine_collection.reset_mock()
        dash.prescribe_medication()
        dash.medicine_collection.insert_one.assert_called_once()
        doc = dash.medicine_collection.insert_one.call_args[0][0]
        assert doc["medication_name"] == "Aspirin"
        assert doc["frequency"] == 1
        assert doc["medication_intake_frequency"] == "Daily"

    def test_no_insert_when_not_submitted(self, dash, stub_imports):
        st_stub, _ = stub_imports
        self._setup_st(
            st_stub,
            name="Aspirin",
            frequency=1,
            time_period="Indefinite",
            intake_freq="Daily",
            dosages=["100mg"],
            times=[MagicMock(__str__=lambda s: "08:00:00")],
            submit=False,
        )
        dash.medicine_collection.reset_mock()
        dash.prescribe_medication()
        dash.medicine_collection.insert_one.assert_not_called()

    def test_document_contains_date_prescribed(self, dash, stub_imports):
        st_stub, _ = stub_imports
        self._setup_st(
            st_stub,
            name="Metformin",
            frequency=2,
            time_period="Indefinite",
            intake_freq="Daily",
            dosages=["500mg", "500mg"],
            times=[
                MagicMock(__str__=lambda s: "08:00:00"),
                MagicMock(__str__=lambda s: "20:00:00"),
            ],
            submit=True,
        )
        dash.medicine_collection.reset_mock()
        dash.prescribe_medication()
        doc = dash.medicine_collection.insert_one.call_args[0][0]
        assert doc["date_prescribed"] == date.today()

    def test_custom_time_period_sets_start_finish(self, dash, stub_imports):
        st_stub, _ = stub_imports
        start = date(2026, 1, 1)
        finish = date(2026, 6, 30)
        st_stub.text_input.return_value = "Lisinopril"
        st_stub.number_input.return_value = 1
        st_stub.selectbox.side_effect = ["Custom", "Daily"]
        st_stub.date_input.side_effect = [start, finish]
        st_stub.time_input.side_effect = [MagicMock(__str__=lambda s: "09:00:00")]
        form_cm = MagicMock()
        form_cm.__enter__ = MagicMock(return_value=form_cm)
        form_cm.__exit__ = MagicMock(return_value=False)
        st_stub.form.return_value = form_cm
        st_stub.form_submit_button.return_value = True

        dash.medicine_collection.reset_mock()
        dash.prescribe_medication()
        doc = dash.medicine_collection.insert_one.call_args[0][0]
        assert doc["medication_time_period_start"] == str(start)
        assert doc["medication_time_period_finish"] == str(finish)


# ---------------------------------------------------------------------------
# cancel_medication — selectbox + delete logic
# ---------------------------------------------------------------------------

class TestCancelMedication:
    def test_delete_called_for_selected_medication(self, dash, stub_imports):
        st_stub, _ = stub_imports
        from bson import ObjectId
        oid = ObjectId()
        dash.medicine_collection.find.return_value = [
            {"_id": oid, "medication_name": "Aspirin"}
        ]
        st_stub.selectbox.return_value = "Aspirin"
        st_stub.button.return_value = True  # "Cancel Medication" pressed

        dash.medicine_collection.reset_mock()
        # st.rerun raises StopException in real Streamlit; mock it as a no-op
        st_stub.rerun.return_value = None
        dash.cancel_medication()

        dash.medicine_collection.delete_one.assert_called_once_with({"_id": oid})

    def test_no_delete_when_button_not_pressed(self, dash, stub_imports):
        st_stub, _ = stub_imports
        from bson import ObjectId
        oid = ObjectId()
        dash.medicine_collection.find.return_value = [
            {"_id": oid, "medication_name": "Ibuprofen"}
        ]
        st_stub.selectbox.return_value = "Ibuprofen"
        st_stub.button.return_value = False

        dash.medicine_collection.reset_mock()
        dash.cancel_medication()
        dash.medicine_collection.delete_one.assert_not_called()

    def test_shows_info_when_no_medications(self, dash, stub_imports):
        st_stub, _ = stub_imports
        dash.medicine_collection.find.return_value = []
        st_stub.reset_mock()
        dash.cancel_medication()
        st_stub.info.assert_called_once()


# ---------------------------------------------------------------------------
# init_connection
# ---------------------------------------------------------------------------

class TestInitConnection:
    def test_returns_mongo_client(self, stub_imports):
        st_stub, pymongo_stub = stub_imports
        fake_client = MagicMock()
        pymongo_stub.MongoClient.return_value = fake_client
        import caregiver_dash as cd
        result = cd.init_connection()
        assert result is not None

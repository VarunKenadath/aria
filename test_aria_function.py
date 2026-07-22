import pytest
from unittest.mock import patch, MagicMock
from datetime import date, time, timedelta
from dateutil.relativedelta import relativedelta
from fastapi.testclient import TestClient


# --- parse_times unit tests (no DB needed) ---

def test_parse_times_list_input():
    from aria_function import parse_times
    assert parse_times(["08:30:00", "14:00:00"]) == ["08:30", "14:00"]


def test_parse_times_datetime_time_string():
    from aria_function import parse_times
    raw = "[datetime.time(8, 30), datetime.time(14, 0)]"
    assert parse_times(raw) == ["08:30", "14:00"]


def test_parse_times_hhmm_string():
    from aria_function import parse_times
    assert parse_times("08:30 and 14:00") == ["08:30", "14:00"]


def test_parse_times_empty():
    from aria_function import parse_times
    assert parse_times(None) == []
    assert parse_times("no times here") == []


# --- FastAPI endpoint tests ---

@pytest.fixture()
def client():
    with patch("aria_function.MongoClient"), \
         patch("aria_function.os.environ.get", return_value="mongodb://fake"):
        from aria_function import app
        return TestClient(app)


@pytest.fixture(autouse=True)
def reset_day_list():
    import aria_function
    aria_function.medication_day_list.clear()
    yield
    aria_function.medication_day_list.clear()


# POST /symptom

def test_post_symptom_success(client):
    with patch("aria_function.db") as mock_db:
        mock_db.__getitem__.return_value.insert_one.return_value = MagicMock()
        resp = client.post("/symptom", json={"symptom": "headache", "severity": "mild"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success"}


def test_post_symptom_missing_field(client):
    resp = client.post("/symptom", json={"symptom": "headache"})
    assert resp.status_code == 422


def test_post_symptom_db_error(client):
    with patch("aria_function.db") as mock_db:
        mock_db.__getitem__.return_value.insert_one.side_effect = Exception("DB down")
        resp = client.post("/symptom", json={"symptom": "nausea", "severity": "severe"})
    assert resp.status_code == 500
    assert "DB down" in resp.json()["detail"]


# GET /medicine

def test_get_medication_success(client):
    fake_meds = [{"medication_name": "Aspirin", "frequency": 1}]
    with patch("aria_function.medications") as mock_col:
        mock_col.find.return_value = iter(fake_meds)
        resp = client.get("/medicine")
    assert resp.status_code == 200
    assert resp.json() == fake_meds


def test_get_medication_db_error(client):
    with patch("aria_function.medications") as mock_col:
        mock_col.find.side_effect = Exception("connection failed")
        resp = client.get("/medicine")
    assert resp.status_code == 500


# GET /medication_routine — frequency variants

def _med(name, frequency, dosages, times):
    return {
        "medication_name": name,
        "medication_intake_frequency": frequency,
        "dosages": dosages,
        "time": times,
        "date_prescribed": date.today(),
    }


def test_routine_daily(client):
    med = _med("Aspirin", "Daily", ["100mg"], ["08:00:00"])
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert "Today take 100mg of Aspirin at 08:00" in resp.json()["routine"]


def test_routine_empty_when_no_meds(client):
    with patch("aria_function.get_medication", return_value=[]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert resp.json() == {"routine": []}


def test_routine_alternate_days_mon_wed_fri_sun_match(client):
    med = _med("Ibuprofen", "Alternate days (Mon,Wed,Fri,Sun)", ["200mg"], ["09:00:00"])
    today_abbr = date.today().strftime("%a")
    if today_abbr not in ("Mon", "Wed", "Fri", "Sun"):
        pytest.skip("Today is not a Mon/Wed/Fri/Sun — skipping match branch")
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_alternate_days_tue_thu_sat_no_match(client):
    med = _med("Ibuprofen", "Alternate days (Tue,Thurs,Sat)", ["200mg"], ["09:00:00"])
    today_abbr = date.today().strftime("%a")
    if today_abbr in ("Tue", "Thurs", "Sat"):
        pytest.skip("Today matches Tue/Thurs/Sat — skipping no-match branch")
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert resp.json()["routine"] == []


def test_routine_fortnightly_match(client):
    prescribed = date.today() - timedelta(days=14)
    med = {**_med("Metformin", "Fortnightly", ["500mg"], ["07:00:00"]),
           "date_prescribed": prescribed}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_fortnightly_no_match(client):
    prescribed = date.today() - timedelta(days=7)
    med = {**_med("Metformin", "Fortnightly", ["500mg"], ["07:00:00"]),
           "date_prescribed": prescribed}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert resp.json()["routine"] == []


def test_routine_fortnightly_missing_date_prescribed(client):
    med = {
        "medication_name": "Metformin",
        "medication_intake_frequency": "Fortnightly",
        "dosages": ["500mg"],
        "time": ["07:00:00"],
    }
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 422


def test_routine_monthly_match(client):
    prescribed = date.today() - relativedelta(months=1)
    med = {**_med("Lisinopril", "Monthly", ["10mg"], ["08:00:00"]),
           "date_prescribed": prescribed}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_annually_match(client):
    prescribed = date.today() - relativedelta(years=1)
    med = {**_med("Flu Shot", "Annually", ["1 dose"], ["10:00:00"]),
           "date_prescribed": prescribed}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_custom_days_match(client):
    today_full = date.today().strftime("%A")
    med = {**_med("Vitamin D", "Custom days", ["1000IU"], ["08:00:00"]),
           "custom_days": [today_full]}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_custom_days_no_match(client):
    other_days = [d for d in ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                  if d != date.today().strftime("%A")]
    med = {**_med("Vitamin D", "Custom days", ["1000IU"], ["08:00:00"]),
           "custom_days": [other_days[0]]}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert resp.json()["routine"] == []


def test_routine_custom_days_missing_custom_days(client):
    med = {
        "medication_name": "Vitamin D",
        "medication_intake_frequency": "Custom days",
        "dosages": ["1000IU"],
        "time": ["08:00:00"],
    }
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 422


def test_routine_custom_dates_match(client):
    med = {**_med("Antibiotic", "Custom dates", ["250mg"], ["12:00:00"]),
           "custom_dates": date.today()}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert len(resp.json()["routine"]) == 1


def test_routine_custom_dates_no_match(client):
    med = {**_med("Antibiotic", "Custom dates", ["250mg"], ["12:00:00"]),
           "custom_dates": date.today() - timedelta(days=1)}
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    assert resp.json()["routine"] == []


def test_routine_missing_dosages(client):
    med = {
        "medication_name": "Aspirin",
        "medication_intake_frequency": "Daily",
        "time": ["08:00:00"],
    }
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 422


def test_routine_missing_time(client):
    med = {
        "medication_name": "Aspirin",
        "medication_intake_frequency": "Daily",
        "dosages": ["100mg"],
        "time": "",
    }
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 422


def test_routine_multiple_doses_per_day(client):
    med = _med("Metformin", "Daily", ["500mg", "500mg"], ["08:00:00", "20:00:00"])
    with patch("aria_function.get_medication", return_value=[med]):
        resp = client.get("/medication_routine")
    assert resp.status_code == 200
    routine = resp.json()["routine"]
    assert len(routine) == 2
    assert any("08:00" in r for r in routine)
    assert any("20:00" in r for r in routine)
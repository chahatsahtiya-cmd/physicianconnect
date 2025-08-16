import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Physician Meeting Scheduler", page_icon="🩺", layout="centered")

# Simple in-memory storage (resets on reload)
if "meetings" not in st.session_state:
    st.session_state["meetings"] = []

st.title("🩺 Physician–Patient Meeting Scheduler")

tabs = st.tabs(["Physician", "Patient"])

# ------------------- Physician tab -------------------
with tabs[0]:
    st.header("👩‍⚕️ Add a new meeting")
    with st.form("add_meeting"):
        physician = st.text_input("Physician Name")
        patient = st.text_input("Patient Name")
        date = st.date_input("Meeting Date")
        time = st.time_input("Meeting Time")
        link = st.text_input("Meeting Link (Zoom/Google Meet etc.)")
        submitted = st.form_submit_button("Save Meeting")
        
        if submitted:
            if physician and patient and link:
                st.session_state["meetings"].append({
                    "physician": physician,
                    "patient": patient,
                    "datetime": datetime.combine(date, time),
                    "link": link
                })
                st.success("✅ Meeting saved!")
            else:
                st.error("Please fill all required fields.")

    if st.session_state["meetings"]:
        st.subheader("All Scheduled Meetings")
        [for] m in st.session_state["meetings"]:

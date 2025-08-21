import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient, errors
from bson.objectid import ObjectId
from datetime import datetime

# ---------------------------------------------------------------------
# 1. PAGE CONFIGURATION
# ---------------------------------------------------------------------
# Use an emoji for a more engaging title
st.set_page_config(
    page_title="TaskMaster Pro",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------
# 2. DATABASE CONNECTION & UTILITIES
# ---------------------------------------------------------------------
# Use @st.cache_resource to establish the connection only once.
@st.cache_resource
def init_connection():
    """Initializes a connection to the MongoDB database. Returns the client object."""
    try:
        client = MongoClient(st.secrets["mongo"]["uri"])
        return client
    except errors.ConnectionFailure as e:
        st.error(f"Could not connect to MongoDB: {e}")
        st.stop() # App can't run without a db, so we stop here.
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.stop()

# Initialize the connection
client = init_connection()

# Ping the database to confirm a successful connection and show a one-time toast.
try:
    client.admin.command('ping')
    # Use session_state to ensure the success message is shown only once per session
    if "db_connection_success" not in st.session_state:
        st.toast("Database connection successful!", icon="🎉")
        st.session_state.db_connection_success = True
except Exception as e:
    st.error(f"Database is not responsive: {e}")
    st.stop()

# Get the database and collection
db = client["taskmaster_db"]
tasks_collection = db["tasks"]

# Define constants for options to avoid magic strings
STATUS_OPTIONS = ["Pending", "In Progress", "Completed"]
PRIORITY_OPTIONS = ["High", "Medium", "Low"]

# ---------------------------------------------------------------------
# 3. SIDEBAR - ADD NEW TASK
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("👤 User")
    # Simple username input for multi-user functionality
    username = st.text_input("Enter your name to see your tasks:", placeholder="e.g., Alex")

    if username.strip(): # Only show the "Add Task" form if a username is entered
        st.header("🚀 Add a New Task")
        with st.form("new_task_form", clear_on_submit=True):
            task_name = st.text_input("Task Name", placeholder="e.g., Finish project report")
            task_priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=1)
            task_due_date = st.date_input("Due Date")
            
            submitted = st.form_submit_button("Add Task", type="primary", use_container_width=True)

            if submitted:
                if not task_name.strip():
                    st.warning("Please enter a task name.", icon="⚠️")
                else:
                    task_data = {
                        "Username": username.strip(), # <-- ADDED: Link task to the user
                        "Task": task_name.strip(),
                        "Status": "Pending",
                        "Priority": task_priority,
                        "DueDate": datetime.combine(task_due_date, datetime.min.time()),
                        "CreatedAt": datetime.utcnow()
                    }
                    tasks_collection.insert_one(task_data) # <-- MODIFIED
                    st.toast(f"Task '{task_name}' added!", icon="✅")

# ---------------------------------------------------------------------
# 4. MAIN PAGE - HEADER & OVERVIEW
# ---------------------------------------------------------------------
st.title("TaskMaster Dashboard")
st.markdown(f"Managing tasks for: **{username}**" if username.strip() else "Enter your full name in the sidebar to begin.")

# Fetch tasks ONLY for the current user
if username.strip():
    try:
        # <-- MODIFIED: Added {"Username": username.strip()} filter
        all_tasks = list(tasks_collection.find({"Username": username.strip()}).sort("CreatedAt", -1))
    except Exception as e:
        st.error(f"Failed to fetch tasks: {e}")
        all_tasks = []

else:
    all_tasks = []
    st.info("Please enter your name in the sidebar to load your tasks.")
# KPI Metrics
total_tasks = len(all_tasks)
completed_tasks = sum(1 for t in all_tasks if t["Status"] == "Completed")
pending_tasks = total_tasks - completed_tasks

st.subheader("📊 Project Overview")
kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric(label="Total Tasks", value=total_tasks)
kpi2.metric(label="Completed ✅", value=completed_tasks)
kpi3.metric(label="Pending ⏳", value=pending_tasks)

# ---------------------------------------------------------------------
# 5. VISUALIZATION & DATA DISPLAY
# ---------------------------------------------------------------------
c1, c2 = st.columns((7, 5))

with c1:
    st.subheader("Task Status Distribution")
    if total_tasks > 0:
        status_counts = pd.Series([t["Status"] for t in all_tasks]).value_counts()
        fig = px.pie(
            status_counts,
            values=status_counts.values,
            names=status_counts.index,
            title=" ", # Title is already a subheader
            color=status_counts.index,
            color_discrete_map={
                "Completed": "#4CAF50",
                "In Progress": "#FFC107",
                "Pending": "#F44336"
            }
        )
        fig.update_layout(showlegend=False)
        fig.update_traces(textinfo='percent+label', textfont_size=16)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Add a task to see the status distribution chart.")

with c2:
    st.subheader("🗓️ Upcoming Deadlines")
    if username.strip() and pending_tasks > 0:
        pending_df = pd.DataFrame([
            {
                "Task": t["Task"],
                "Priority": t.get("Priority", "Medium"),
                "DueDate": t.get("DueDate", "N/A")
            }
            for t in all_tasks if t["Status"] != "Completed"
        ])
        
        # Convert to datetime for proper sorting
        pending_df["DueDate"] = pd.to_datetime(pending_df["DueDate"], errors='coerce')
        pending_df.dropna(subset=["DueDate"], inplace=True) # Remove tasks without a valid date
        
        # Sort by DueDate so the most urgent tasks are at the top
        pending_df = pending_df.sort_values(by="DueDate").reset_index(drop=True)
        
        st.dataframe(
            pending_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Task": st.column_config.TextColumn("Task Name", width="medium"),
                "Priority": st.column_config.TextColumn("Priority"),
                "DueDate": st.column_config.DateColumn("Due Date", format="YYYY-MM-DD")
            }
        )
    elif username.strip():
        st.info("No pending tasks with deadlines.")

# ---------------------------------------------------------------------
# 6. EDITABLE TASK LIST
# ---------------------------------------------------------------------
st.subheader("📝 Manage Your Tasks")

# Filtering controls
if all_tasks:
    filter_status = st.multiselect(
        "Filter by Status",
        options=STATUS_OPTIONS,
        default=STATUS_OPTIONS
    )
    
    filtered_tasks = [t for t in all_tasks if t["Status"] in filter_status]
    
    # Display tasks
    for task in filtered_tasks:
        task_id_str = str(task["_id"])
        with st.form(key=f"task_form_{task_id_str}"):
            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 1, 1])
            
            with c1:
                new_task_name = st.text_input("Task", value=task["Task"], label_visibility="collapsed")
            with c2:
                new_status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(task["Status"]), label_visibility="collapsed")
            with c3:
                new_priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(task.get("Priority", "Medium")), label_visibility="collapsed")
            with c4:
                if st.form_submit_button("Save", use_container_width=True):
                    updates = {
                        "Task": new_task_name.strip(),
                        "Status": new_status,
                        "Priority": new_priority
                    }
                    tasks_collection.update_one({"_id": task["_id"]}, {"$set": updates})
                    st.toast("Task updated!", icon="🔄")
                    st.rerun() # Rerun to reflect changes immediately
            with c5:
                if st.form_submit_button("Delete", type="secondary", use_container_width=True):
                    tasks_collection.delete_one({"_id": task["_id"]})
                    st.toast(f"Task '{task['Task']}' deleted.", icon="🗑️")
                    st.rerun()
else:
    st.info("No tasks found. Add your first task from the sidebar!", icon="☝️")
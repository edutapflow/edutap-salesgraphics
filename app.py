import sys
import asyncio
import datetime
import zipfile
import io

# --- FIX: Force Windows to use the correct Asyncio Event Loop for Subprocesses ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import os
import uuid
import json
from jinja2 import Environment, FileSystemLoader
from PIL import Image
from playwright.sync_api import sync_playwright

# --- UI Configuration (MUST BE THE VERY FIRST STREAMLIT COMMAND) ---
st.set_page_config(page_title="EduTap Asset Generator", layout="wide", initial_sidebar_state="collapsed")

# --- Cloud Server Chrome Installer ---
@st.cache_resource
def install_playwright():
    os.system("playwright install chromium")

install_playwright()

# --- Directory Setup ---
OUTPUT_DIR = os.path.abspath("output").replace("\\", "/")
os.makedirs(OUTPUT_DIR, exist_ok=True)
env = Environment(loader=FileSystemLoader('templates'))

# --- Persistent Data Configuration ---
CONFIG_FILE = "dropdown_config.json"

def load_config():
    default_config = {
        "CAMPAIGNS": ["Super Sale", "Maha Sale", "Flash Sale", "Wow Sale"],
        "EXAMS": [
            "", "RBI Grade B", "RBI Grade A/B", "SEBI Grade A", "NABARD Grade A", 
            "IRDAI Grade A", "PFRDA Grade A", "IFSCA Grade A", "UPSC CSAT", 
            "UPSC EPFO APFC & EO/AO", "JAIIB", "Banking Exams"
        ],
        "STREAMS": ["", "General Stream"],
        "SUBJECTS": ["", "Quant", "Reasoning", "English", "AFM", "PPB", "IF&IFS", "RBWM", "ABM", "BFM", "ABFM", "BRBL", "Maths"],
        "OFFERINGS": [
            "Gold", "Silver", "Test Series", "Crash Course", "Master Course", 
            "Live Crash Course", "Special Subjects", "Super Crash Course", 
            "Banker's Capsule Course", "Mahapack", "Combo", "Quick Revision Batch"
        ]
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                for k in default_config.keys():
                    if k not in user_config:
                        user_config[k] = default_config[k]
                return user_config
        except Exception:
            return default_config
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

if 'config' not in st.session_state:
    st.session_state.config = load_config()

if 'boxes' not in st.session_state:
    st.session_state.boxes = [str(uuid.uuid4())]

# --- GLOBAL PASSWORD PROTECTION ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Access Restricted")
    st.markdown("Please enter the passcode to access the EduTap Asset Generator.")
    app_password = st.text_input("Passcode", type="password")
    
    if st.button("Unlock App"):
        if app_password == "sale@321":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect Passcode. Access Denied.")
    st.stop() 

def add_box():
    if len(st.session_state.boxes) < 6:
        st.session_state.boxes.append(str(uuid.uuid4()))

def remove_box(box_id):
    st.session_state.boxes.remove(box_id)

if 'success_popup' in st.session_state:
    st.toast(st.session_state.success_popup, icon="✅")
    del st.session_state.success_popup

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Data Management")
    admin_pass = st.text_input("Admin Password", type="password")
    if admin_pass == "Addme@123":
        st.success("Admin Panel Unlocked")
        category_to_edit = st.selectbox("Select List to Update", ["Sale Campaigns", "Exams", "Streams", "Subjects", "Offerings"])
        new_item = st.text_input(f"New item for {category_to_edit}")
        if st.button("➕ Add Item", use_container_width=True):
            if new_item.strip():
                cat_map = {"Sale Campaigns": "CAMPAIGNS", "Exams": "EXAMS", "Streams": "STREAMS", "Subjects": "SUBJECTS", "Offerings": "OFFERINGS"}
                key = cat_map[category_to_edit]
                if new_item.strip() not in st.session_state.config[key]:
                    st.session_state.config[key].append(new_item.strip())
                    save_config(st.session_state.config)
                    st.session_state.success_popup = f"'{new_item.strip()}' added!"
                    st.rerun() 
                else:
                    st.warning("Item already exists.")
    elif admin_pass != "":
        st.error("Incorrect Password.")

# --- MAIN DASHBOARD ---
st.title("EduTap Sale Graphics Generator")

# --- SECTION 1: Campaign Details ---
st.header("Campaign Configuration")
with st.container():
    col1, col2, col3 = st.columns(3)
    with col1:
        sale_name = st.selectbox("Sale Campaign", st.session_state.config["CAMPAIGNS"])
        discount_type = st.radio("Discount Structure", ["Flat", "Flat + Additional"])
    with col2:
        if discount_type == "Flat":
            flat_val = st.text_input("Flat Discount (%)", "50")
            add_val = None
        else:
            flat_val = st.text_input("Flat Discount (%)", "50")
            add_val = st.text_input("Additional Discount (%)", "40")
        coupon_code = st.text_input("Coupon Code (Max 7 Chars)", "SUPER", max_chars=7)
    with col3:
        default_start = datetime.date.today()
        default_end = default_start + datetime.timedelta(days=1)
        validity_dates = st.date_input("Validity Period", value=(default_start, default_end))
        validity_text = ""
        if len(validity_dates) == 2:
            start_d, end_d = validity_dates
            if start_d.month == end_d.month and start_d.year == end_d.year:
                validity_text = f"*Valid: {start_d.day} to {end_d.day} {start_d.strftime('%b %Y')}*"
            else:
                validity_text = f"*Valid: {start_d.day} {start_d.strftime('%b')} to {end_d.day} {end_d.strftime('%b %Y')}*"

st.divider()

# --- SECTION 2: Course Offerings ---
st.header("Course Alignments")

courses = []
for i, box_id in enumerate(st.session_state.boxes):
    st.markdown(f"**Course Box {i+1}**")
    
    # 1. NEW UI FLOW: The Mode Selector
    mode = st.radio(
        "Exam Mode", 
        ["Single Exam", "Sector", "Combo (Individual)", "Combo (Individual + Sector)"], 
        key=f"mode_{box_id}", 
        horizontal=True
    )
    
    col_a, col_b, col_c = st.columns([3, 2, 3])
    
    main_exam = ""
    sector_name = ""
    stream = ""
    subject = ""
    offerings = []
    
    with col_a:
        if mode == "Single Exam":
            main_exam = st.selectbox("Select Exam", options=st.session_state.config["EXAMS"], key=f"ex_{box_id}")
        elif mode == "Sector":
            sector_name = st.selectbox("Select Sector", options=["Bank Exams"], key=f"sec_{box_id}")
        elif mode == "Combo (Individual)":
            main_exam = st.selectbox("Select Exam", options=st.session_state.config["EXAMS"], key=f"ex_{box_id}")
        elif mode == "Combo (Individual + Sector)":
            sub_col1, sub_col2 = st.columns(2)
            with sub_col1:
                main_exam = st.selectbox("Exam", options=st.session_state.config["EXAMS"], key=f"ex_{box_id}")
            with sub_col2:
                sector_name = st.selectbox("Sector", options=["Bank Exams"], key=f"sec_{box_id}")
                
    with col_b:
        stream = st.selectbox("Stream", options=st.session_state.config["STREAMS"], key=f"str_{box_id}")
        subject = st.selectbox("Subject", options=st.session_state.config["SUBJECTS"], key=f"sub_{box_id}")
        
    with col_c:
        offerings = st.multiselect("Offerings", options=st.session_state.config["OFFERINGS"], default=[], max_selections=4, key=f"off_{box_id}")
        st.write("&nbsp;") 
        if len(st.session_state.boxes) > 1:
            st.button("❌ Remove Box", key=f"del_{box_id}", on_click=remove_box, args=(box_id,))
            
    # Process the Title logic for Jinja
    main_title = ""
    sub_title = ""
    
    if mode == "Single Exam":
        main_title = main_exam
    elif mode == "Sector":
        main_title = sector_name
        if sector_name == "Bank Exams":
            sub_title = "SBI + IBPS + RRB<br>(PO + CLERK)"
    elif mode == "Combo (Individual)":
        main_title = main_exam
        sub_title = "All Combos"
    elif mode == "Combo (Individual + Sector)":
        if main_exam and sector_name:
            main_title = f"{main_exam} <span style='color:#E31E24;'>+</span> {sector_name}"
        else:
            main_title = f"{main_exam}{sector_name}"
        if sector_name == "Bank Exams":
            sub_title = "SBI + IBPS + RRB<br>(PO + CLERK)"
            
    courses.append({
        "main_title": main_title.strip(), 
        "sub_title": sub_title.strip(),
        "stream": stream.strip(),
        "subject": subject.strip(), 
        "offerings": offerings
    })
    st.write("---")

if len(st.session_state.boxes) < 6:
    st.button("➕ Add Another Course Box", on_click=add_box)

st.divider()

# --- SECTION 3: Engine Execution ---
if st.button("Initialize Asset Generation", type="primary", use_container_width=True):
    if len(validity_dates) < 2:
        st.error("Action Required: Please select both a Start Date and End Date.")
    else:
        with st.spinner("Making Graphics. Please wait..."):
            data_payload = {
                "discount_type": discount_type, "flat_val": flat_val, "add_val": add_val,
                "coupon_code": coupon_code, "validity_text": validity_text,
                "expiry_text": "*Offer Expire today midnight*", "courses": courses
            }
            
            folder_path = f"base_images/{sale_name}/"
            if discount_type == "Flat":
                comm_bg = folder_path + "Community_flatdiscount.png"
                yt_bg = folder_path + "ytchannelart_flatdiscount.png"
            else:
                comm_bg = folder_path + "Community_additionaldiscount.png"
                yt_bg = folder_path + "ytchannelart_additionaldiscount.png"

            try:
                comm_template = env.get_template('community_template.html')
                yt_template = env.get_template('yt_template.html')
                
                tasks = [
                    {"name": f"{sale_name}_Comm_Standard.png", "bg": comm_bg, "template": comm_template, "use_expiry": False, "size": (1080, 1080)},
                    {"name": f"{sale_name}_Comm_Expiry.png", "bg": comm_bg, "template": comm_template, "use_expiry": True, "size": (1080, 1080)},
                    {"name": f"{sale_name}_YT_Standard.png", "bg": yt_bg, "template": yt_template, "use_expiry": False, "size": (1600, 900)},
                    {"name": f"{sale_name}_YT_Expiry.png", "bg": yt_bg, "template": yt_template, "use_expiry": True, "size": (1600, 900)}
                ]
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    for task in tasks:
                        data_payload["use_expiry"] = task["use_expiry"]
                        rendered_html = task["template"].render(data=data_payload)
                        safe_name = task['name'].replace(' ', '_')
                        temp_overlay_name = f"temp_{safe_name}"
                        overlay_path = os.path.join(OUTPUT_DIR, temp_overlay_name).replace("\\", "/")
                        final_output_path = os.path.join(OUTPUT_DIR, task["name"]).replace("\\", "/")
                        
                        page = browser.new_page(viewport={"width": task["size"][0], "height": task["size"][1]})
                        page.set_content(rendered_html, wait_until="networkidle")
                        page.wait_for_timeout(500) 
                        page.screenshot(path=overlay_path, omit_background=True)
                        page.close()
                        
                        base_img = Image.open(task['bg']).convert("RGBA")
                        base_img = base_img.resize(task["size"], Image.LANCZOS) 
                        overlay_img = Image.open(overlay_path).convert("RGBA")
                        final_img = Image.alpha_composite(base_img, overlay_img)
                        final_img.save(final_output_path, format="PNG")
                        os.remove(overlay_path)
                    browser.close()
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for task in tasks:
                        final_output_path = os.path.join(OUTPUT_DIR, task["name"]).replace("\\", "/")
                        zip_file.write(final_output_path, arcname=task["name"])
                        os.remove(final_output_path) 
                
                st.success("✅ Done. Note: Download Your Files First Before Refershing or Generating Next Graphics")
                safe_camp_name = sale_name.replace(" ", "_")
                st.download_button(
                    label="📦 Download All Assets (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name=f"{safe_camp_name}_Assets.zip",
                    mime="application/zip",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Render Engine Fault: {str(e)}")

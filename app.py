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

# --- Helper Function for Dates ---
def get_ordinal(n):
    if 11 <= (n % 100) <= 13:
        return str(n) + 'th'
    return str(n) + {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')

# --- UI Configuration ---
st.set_page_config(page_title="EduTap Asset Generator", layout="wide", initial_sidebar_state="collapsed")

@st.cache_resource
def install_playwright():
    os.system("playwright install chromium")
install_playwright()

OUTPUT_DIR = os.path.abspath("output").replace("\\", "/")
os.makedirs(OUTPUT_DIR, exist_ok=True)
env = Environment(loader=FileSystemLoader('templates'))

CONFIG_FILE = "dropdown_config.json"

# --- SMART SCHEMA CONFIGURATION ---
def load_config():
    default_config = {
        "CAMPAIGNS": ["Super Sale", "Maha Sale", "Flash Sale", "Wow Sale"],
        "GLOBAL_OFFERINGS": ["Gold Course", "Silver Course", "Gold Package", "Silver Package", "Test Series", "Crash Course", "Master Course", "Live Crash Course", "Special Subjects", "Special Subject Course", "Super Crash Course", "Banker's Capsule Course", "Mahapack", "Combo", "Quick Revision Batch"],
        "SECTORS": ["Banking Exams"],
        "SUBJECTS_LIST": ["Quant", "Reasoning", "English", "AFM", "PPB", "IF&IFS", "RBWM", "ABM", "BFM", "ABFM", "BRBL", "Maths", "IE-IFS", "IR & Labor Laws", "Accountancy"],
        "EXAMS_SCHEMA": {
            "RBI Grade A/B": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "SEBI Grade A": {"has_stream": True, "has_subject": False, "streams": ["General Stream"], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "NABARD Grade A": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "IRDAI Grade A": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "PFRDA Grade A": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "IFSCA Grade A": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Gold Course", "Silver Course", "Crash Course"]},
            "UPSC CSAT": {"has_stream": False, "has_subject": False, "streams": [], "subjects": [], "offerings": ["Test Series", "Master Course", "Live Crash Course"]},
            "UPSC EPFO APFC & EO/AO": {
                "has_stream": False, "has_subject": True, "streams": [], 
                "subjects": ["IR & Labor Laws", "Accountancy"], 
                "offerings_without_subject": ["Master Course", "Special Subject Course"],
                "offerings_with_subject": ["Master Course"],
                "offerings": ["Master Course", "Special Subject Course"]
            },
            "JAIIB": {
                "has_stream": False, "has_subject": True, "streams": [], 
                "subjects": ["IE-IFS", "PPB", "AFM", "RBWM"], 
                "offerings_without_subject": ["Master Course", "Crash Course", "Test Series"],
                "offerings_with_subject": ["Master Course", "Super Crash Course", "Banker's Capsule Course"],
                "offerings": ["Master Course", "Crash Course", "Test Series"]
            }
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                
                # Auto-Migration: Force updates for existing users to the new dynamic logic
                if "EXAMS_SCHEMA" in user_config:
                    user_config["EXAMS_SCHEMA"]["JAIIB"] = default_config["EXAMS_SCHEMA"]["JAIIB"]
                    user_config["EXAMS_SCHEMA"]["UPSC EPFO APFC & EO/AO"] = default_config["EXAMS_SCHEMA"]["UPSC EPFO APFC & EO/AO"]
                    if "JAIIB (Individual Subjects)" in user_config["EXAMS_SCHEMA"]:
                        del user_config["EXAMS_SCHEMA"]["JAIIB (Individual Subjects)"]
                else:
                    return default_config
                    
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
    app_password = st.text_input("Passcode", type="password")
    if st.button("Unlock App"):
        if app_password == "sale@321":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect Passcode.")
    st.stop() 

def add_box():
    if len(st.session_state.boxes) < 6:
        st.session_state.boxes.append(str(uuid.uuid4()))

def remove_box(box_id):
    st.session_state.boxes.remove(box_id)

if 'success_popup' in st.session_state:
    st.toast(st.session_state.success_popup, icon="✅")
    del st.session_state.success_popup

# --- SIDEBAR: Upgraded Schema Admin Panel ---
with st.sidebar:
    st.header("⚙️ Schema Admin Panel")
    st.markdown("Add new exams dynamically. The UI will adjust automatically.")
    
    admin_pass = st.text_input("Admin Password", type="password")
    if admin_pass == "addme@123":
        st.success("Admin Panel Unlocked")
        
        action = st.radio("What to add?", ["New Exam", "New Subject", "New Sector", "New Global Offering", "New Campaign"])
        
        if action == "New Exam":
            new_ex = st.text_input("Exam Name")
            has_str = st.checkbox("Uses Streams?")
            str_list = st.text_input("Streams (comma separated)") if has_str else ""
            has_sub = st.checkbox("Uses Subjects?")
            sub_list = st.text_input("Subjects (comma separated)") if has_sub else ""
            
            if has_sub:
                off_no_sub = st.multiselect("Offerings (When NO Subject selected)", options=st.session_state.config["GLOBAL_OFFERINGS"])
                off_with_sub = st.multiselect("Offerings (When Subject IS selected)", options=st.session_state.config["GLOBAL_OFFERINGS"])
                allowed_off = off_no_sub 
            else:
                allowed_off = st.multiselect("Allowed Offerings", options=st.session_state.config["GLOBAL_OFFERINGS"])
                off_no_sub = allowed_off
                off_with_sub = allowed_off
            
            if st.button("Save Exam Configuration", use_container_width=True):
                if new_ex:
                    st.session_state.config["EXAMS_SCHEMA"][new_ex] = {
                        "has_stream": has_str,
                        "has_subject": has_sub,
                        "streams": [s.strip() for s in str_list.split(",") if s.strip()],
                        "subjects": [s.strip() for s in sub_list.split(",") if s.strip()],
                        "offerings": allowed_off,
                        "offerings_without_subject": off_no_sub,
                        "offerings_with_subject": off_with_sub
                    }
                    save_config(st.session_state.config)
                    st.session_state.success_popup = f"Added {new_ex} to Database!"
                    st.rerun()
                    
        else:
            new_item = st.text_input(f"New item for {action}")
            if st.button("➕ Add Item", use_container_width=True):
                if new_item.strip():
                    key_map = {"New Subject": "SUBJECTS_LIST", "New Sector": "SECTORS", "New Global Offering": "GLOBAL_OFFERINGS", "New Campaign": "CAMPAIGNS"}
                    key = key_map[action]
                    if new_item.strip() not in st.session_state.config[key]:
                        st.session_state.config[key].append(new_item.strip())
                        save_config(st.session_state.config)
                        st.session_state.success_popup = f"Added {new_item.strip()}!"
                        st.rerun()

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
                validity_text = f"*Valid: {start_d.day} to {end_d.day} {start_d.strftime('%B %Y')}*"
            else:
                validity_text = f"*Valid: {start_d.day} {start_d.strftime('%B')} to {end_d.day} {end_d.strftime('%B %Y')}*"

st.divider()

# --- SECTION 2: Course Offerings (DYNAMIC UI) ---
st.header("Course Alignments")

courses = []
for i, box_id in enumerate(st.session_state.boxes):
    st.markdown(f"**Course Box {i+1}**")
    
    modes = ["Single Exam", "Single Subject", "Sector", "Combo (Individual)", "Combo (Individual + Sector)"]
    mode = st.radio("Exam Mode", modes, key=f"mode_{box_id}", horizontal=True)
    
    stream_val = ""
    subject_val = []
    main_title = ""
    sub_title = ""
    offerings = []
    
    if mode in ["Single Exam", "Combo (Individual)"]:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            exam = st.selectbox("Select Exam", options=list(st.session_state.config["EXAMS_SCHEMA"].keys()), key=f"ex_{box_id}")
            
        schema = st.session_state.config["EXAMS_SCHEMA"].get(exam, {})
        
        with col2:
            if schema.get("has_stream"):
                stream_val = st.selectbox("Stream", options=schema.get("streams", []), key=f"str_{box_id}")
        with col3:
            if schema.get("has_subject"):
                # Multi-select subject enabled
                subject_val = st.multiselect("Subjects", options=schema.get("subjects", []), key=f"sub_{box_id}")
        with col4:
            # Dynamic Offering intelligence
            available_offs = schema.get("offerings", [])
            if schema.get("has_subject"):
                if len(subject_val) > 0 and "offerings_with_subject" in schema:
                    available_offs = schema["offerings_with_subject"]
                elif len(subject_val) == 0 and "offerings_without_subject" in schema:
                    available_offs = schema["offerings_without_subject"]
                    
            offerings = st.multiselect("Offerings", options=available_offs, key=f"off_{box_id}")
            if len(st.session_state.boxes) > 1: st.button("❌ Remove Box", key=f"del_{box_id}", on_click=remove_box, args=(box_id,))
            
        main_title = exam
        if mode == "Combo (Individual)":
            sub_title = "All Combos"
            
        subject_str = ", ".join(subject_val) if subject_val else ""
            
        courses.append({
            "is_split": False, "main_title": main_title.strip(), "sub_title": sub_title.strip(),
            "stream": stream_val.strip(), "subject": subject_str.strip(), "offerings": offerings
        })

    elif mode == "Single Subject":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            subj_title_list = st.multiselect("Select Subject(s)", options=st.session_state.config["SUBJECTS_LIST"], key=f"subjmode_{box_id}")
            subj_title = ", ".join(subj_title_list)
        with col2:
            target_exam = st.selectbox("Target Exam (Subtitle)", options=[""] + st.session_state.config["SECTORS"] + list(st.session_state.config["EXAMS_SCHEMA"].keys()), key=f"target_{box_id}")
        with col4:
            offerings = st.multiselect("Offerings", options=st.session_state.config["GLOBAL_OFFERINGS"], key=f"off_{box_id}")
            if len(st.session_state.boxes) > 1: st.button("❌ Remove Box", key=f"del_{box_id}", on_click=remove_box, args=(box_id,))
            
        courses.append({
            "is_split": False, "main_title": subj_title.strip(), "sub_title": target_exam.strip(),
            "stream": "", "subject": "", "offerings": offerings
        })

    elif mode == "Sector":
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            sector = st.selectbox("Select Sector", options=st.session_state.config["SECTORS"], key=f"sec_{box_id}")
        with col4:
            offerings = st.multiselect("Offerings", options=st.session_state.config["GLOBAL_OFFERINGS"], key=f"off_{box_id}")
            if len(st.session_state.boxes) > 1: st.button("❌ Remove Box", key=f"del_{box_id}", on_click=remove_box, args=(box_id,))
            
        sub_t = "SBI + IBPS + RRB<br>(PO + CLERK)" if sector == "Banking Exams" else ""
        courses.append({
            "is_split": False, "main_title": sector.strip(), "sub_title": sub_t,
            "stream": "", "subject": "", "offerings": offerings
        })

    elif mode == "Combo (Individual + Sector)":
        st.markdown("↳ *Left Side (Exam)*")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ex1 = st.selectbox("Exam", options=list(st.session_state.config["EXAMS_SCHEMA"].keys()), key=f"ex1_{box_id}")
        schema1 = st.session_state.config["EXAMS_SCHEMA"].get(ex1, {})
        str1 = ""; sub1_list = []
        with c2:
            if schema1.get("has_stream"): str1 = st.selectbox("Stream", options=schema1.get("streams", []), key=f"str1_{box_id}")
        with c3:
            if schema1.get("has_subject"): sub1_list = st.multiselect("Subjects", options=schema1.get("subjects", []), key=f"sub1_{box_id}")
        
        available_offs1 = schema1.get("offerings", [])
        if schema1.get("has_subject"):
            if len(sub1_list) > 0 and "offerings_with_subject" in schema1:
                available_offs1 = schema1["offerings_with_subject"]
            elif len(sub1_list) == 0 and "offerings_without_subject" in schema1:
                available_offs1 = schema1["offerings_without_subject"]
                
        with c4:
            off1 = st.multiselect("Offerings", options=available_offs1, key=f"off1_{box_id}")

        st.markdown("↳ *Right Side (Sector)*")
        c5, c6, c7, c8 = st.columns(4)
        with c5:
            ex2 = st.selectbox("Sector", options=st.session_state.config["SECTORS"], key=f"ex2_{box_id}")
        with c8:
            off2 = st.multiselect("Offerings", options=st.session_state.config["GLOBAL_OFFERINGS"], key=f"off2_{box_id}")
            if len(st.session_state.boxes) > 1: st.button("❌ Remove Box", key=f"del_{box_id}", on_click=remove_box, args=(box_id,))
        
        ex2_sub = "SBI + IBPS + RRB<br>(PO + CLERK)" if ex2 == "Banking Exams" else ""
        sub1_str = ", ".join(sub1_list) if sub1_list else ""
        
        courses.append({
            "is_split": True, "exam1_title": ex1.strip(), "exam1_sub": "",
            "stream1": str1.strip(), "subj1": sub1_str.strip(), "offer1": off1,
            "exam2_title": ex2.strip(), "exam2_sub": ex2_sub,
            "stream2": "", "subj2": "", "offer2": off2
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
        with st.spinner("Making Graphics and Generating Promo Text. Please wait..."):
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

            safe_camp_name = sale_name.replace(" ", "_")

            try:
                comm_template = env.get_template('community_template.html')
                yt_template = env.get_template('yt_template.html')
                
                tasks = [
                    {"name": f"{safe_camp_name}_Comm_Standard.png", "bg": comm_bg, "template": comm_template, "use_expiry": False, "size": (1080, 1080)},
                    {"name": f"{safe_camp_name}_Comm_Expiry.png", "bg": comm_bg, "template": comm_template, "use_expiry": True, "size": (1080, 1080)},
                    {"name": f"{safe_camp_name}_YT_Standard.png", "bg": yt_bg, "template": yt_template, "use_expiry": False, "size": (1600, 900)},
                    {"name": f"{safe_camp_name}_YT_Expiry.png", "bg": yt_bg, "template": yt_template, "use_expiry": True, "size": (1600, 900)}
                ]
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    for task in tasks:
                        data_payload["use_expiry"] = task["use_expiry"]
                        rendered_html = task["template"].render(data=data_payload)
                        
                        temp_overlay_name = f"temp_{task['name']}"
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
                
                # --- GENERATE TELEGRAM PROMO TEXT ---
                if discount_type == "Flat":
                    dist_str = f"flat {flat_val}%"
                else:
                    dist_str = f"flat {flat_val}% + additional {add_val}%"
                    
                end_date = validity_dates[1]
                ordinal_day = get_ordinal(end_date.day)
                formatted_month_year = end_date.strftime("%B, %Y")
                final_date_str = f"{ordinal_day} {formatted_month_year}"
                
                course_lines = []
                for c in courses:
                    if c.get("is_split"):
                        title = f"{c['exam1_title']} + {c['exam2_title']}"
                        combined_offs = []
                        for o in c['offer1'] + c['offer2']:
                            if o not in combined_offs:
                                combined_offs.append(o)
                        offer_str = " | ".join(combined_offs)
                    else:
                        # SMART FALLBACK HIERARCHY
                        if c.get('main_title'):
                            title = c['main_title']
                        elif c.get('subject'):
                            title = c['subject']
                        elif c.get('stream'):
                            title = c['stream']
                        else:
                            title = "Course"
                            
                        offer_str = " | ".join(c['offerings'])
                        
                    if offer_str:
                        course_lines.append(f"✅ {title}: {offer_str}")
                    else:
                        course_lines.append(f"✅ {title}")
                        
                course_list_str = "\n".join(course_lines)
                
                promo_text = f"""**😀😀 {sale_name} is here!!**

🥳🥳 Avail a **{dist_str} off** on:

{course_list_str}

Use Code: **{coupon_code}**

The offer is valid till {final_date_str}!!

🎯 Subscribe here: https://edutap.in/courses/"""

                st.session_state['generated_zip'] = zip_buffer.getvalue()
                st.session_state['generated_promo'] = promo_text
                st.session_state['generated_name'] = safe_camp_name
                st.session_state['generation_done'] = True
                
            except Exception as e:
                st.error(f"Render Engine Fault: {str(e)}")

# --- SECTION 4: Output Rendering ---
if st.session_state.get('generation_done'):
    st.success("✅ Done! Your Assets and Text are ready below.")
    
    st.download_button(
        label="📦 Download All Assets (ZIP)",
        data=st.session_state['generated_zip'],
        file_name=f"{st.session_state['generated_name']}_Assets.zip",
        mime="application/zip",
        use_container_width=True
    )
    
    st.divider()
    st.subheader("📝 Telegram Promo Text")
    st.markdown("Hover over the block below and click the **Copy** icon in the top right corner.")
    st.code(st.session_state['generated_promo'], language="text")

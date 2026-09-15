"""Seeds applied exams into the dedicated Notion tracker database."""

import requests
from gov_exam_scraper.models import ScraperSettings

settings = ScraperSettings()
api_key = settings.notion_api_key.get_secret_value()
db_id = "535459a2751646f4906c7c5e03f337ef"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

print("🔧 [1/2] Verifying and configuring Notion database properties...")
db_resp = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers, timeout=30)
if db_resp.status_code != 200:
    print(f"❌ Failed to reach database ({db_resp.status_code}): {db_resp.text}")
    print("Ensure the Notion Integration is invited/connected to this new page.")
    exit(1)

# Add schema properties if missing
patch_payload = {
    "properties": {
        "Authority": {"select": {}},
        "Notification No": {"rich_text": {}},
        "Registration No": {"rich_text": {}},
        "Status": {"select": {}},
        "Exam Date": {"date": {}},
        "Exam Timeline": {"rich_text": {}},
        "Notice Board URL": {"url": {}},
        "Admit Card URL": {"url": {}},
        "Latest News": {"rich_text": {}},
        "Last Checked": {"date": {}},
    }
}
requests.patch(f"https://api.notion.com/v1/databases/{db_id}", headers=headers, json=patch_payload, timeout=30)

APPLIED_EXAMS = [
    {
        "name": "KPSC Gazetted Probationers Group A & B 2026-27",
        "authority": "KPSC",
        "advt_no": "KPSCKA/EXA1/EXMF/9/2026-EXAM-1/I/251710/2026",
        "reg_no": "20260800024990",
        "status": "Exam Scheduled",
        "exam_date": "2026-11-15",
        "timeline": "Prelims: 15 Nov 2026 | Mains: 12, 14, 16, 18 Feb 2027",
        "notice_url": "https://kpsc.kar.nic.in/",
        "latest_news": "Prelims officially scheduled for Nov 15, 2026. Hall tickets expected early November.",
    },
    {
        "name": "KFD Forest Watcher Group D Recruitment 2026",
        "authority": "KFD",
        "advt_no": "A2/Staff/FW/2026-27 (20-07-2026)",
        "reg_no": "20260015389",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "1:20 Selection Merit List -> PST / PET / Physical Efficiency Test",
        "notice_url": "https://aranya.gov.in/",
        "latest_news": "Awaiting 1:20 merit list release for physical endurance and standard test schedule.",
    },
    {
        "name": "NICL 500 Assistants Recruitment 2026",
        "authority": "NICL",
        "advt_no": "RECRUITMENT OF 500 ASSISTANTS (18-07-2026)",
        "reg_no": "Reg: 852296324 | Prelims Roll: 1631001626",
        "status": "Prelims Done - Mains Pending",
        "exam_date": "2026-10-30",
        "timeline": "Phase I (Prelims) completed 27 Aug 2026 | Phase II (Mains): 30 Oct 2026",
        "notice_url": "https://nationalinsurance.nic.co.in/en/recruitment",
        "latest_news": "Phase I Prelims completed. Phase II Main Exam scheduled for October 30, 2026.",
    },
    {
        "name": "IBPS Customer Service Associate (CRP CSA-XVI)",
        "authority": "IBPS",
        "advt_no": "CRP CSA -XVI (Vacancies of 2027-28)",
        "reg_no": "2710512126",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "Prelims: October 2026 (Tentative) | Mains: December 2026",
        "notice_url": "https://www.ibps.in/",
        "latest_news": "Online Preliminary Exam tentatively slated for October 2026. Exact dates pending.",
    },
    {
        "name": "RRB Bengaluru Section Controller (CEN 03/2026)",
        "authority": "RRB",
        "advt_no": "CEN No. 03/2026",
        "reg_no": "C32628792324",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "CBT & CBAT Aptitude Test Schedule to be announced",
        "notice_url": "https://www.rrbbnc.gov.in/",
        "latest_news": "Application window concluded August 14. CBT examination date schedule awaited.",
    },
    {
        "name": "HAL Design Trainee / Management Trainee 2026",
        "authority": "HAL",
        "advt_no": "HAL/CHRC-TM/RECT-02/2026",
        "reg_no": "App No: D327228 | Roll: DING12000305",
        "status": "Exam Scheduled",
        "exam_date": "2026-09-06",
        "timeline": "Selection Test: 06 Sept 2026 (2:00-4:30 PM) | Results: 10 Sept | Interviews: 21-25 Sept",
        "notice_url": "https://hal-india.co.in/Career_Listing.aspx",
        "latest_news": "CRITICAL: Exam on Sept 6, 2026! Ensure Hall Ticket is downloaded.",
    },
    {
        "name": "KEA Village Administrative Officer (VAO) & Land Surveyor",
        "authority": "KEA",
        "advt_no": "VAO-RK & LAND SURVEYOR-RK",
        "reg_no": "App ID: 267000001277482 | Student ID: 1277482",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "Competitive Written Examination Date to be published by KEA",
        "notice_url": "https://cetonline.karnataka.gov.in/kea/",
        "latest_news": "Application submitted. Monitoring KEA announcements board for examination time table.",
    },
    {
        "name": "SBI Junior Associates (Customer Support & Sales)",
        "authority": "SBI",
        "advt_no": "CRPD/CR/2026-27/17",
        "reg_no": "2720047905",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "Preliminary Exam: September 2026 (Tentative) | Main Exam: November 2026",
        "notice_url": "https://sbi.co.in/web/careers/current-openings",
        "latest_news": "Tentative Preliminary Exam month: September 2026. Hall ticket circular awaited.",
    },
    {
        "name": "RRB Bengaluru Junior Engineers (CEN 04/2026)",
        "authority": "RRB",
        "advt_no": "CEN No. 04/2026",
        "reg_no": "C42628792324",
        "status": "Date TBD",
        "exam_date": None,
        "timeline": "CBT Schedule (Electronics & Allied Engineering) to be updated",
        "notice_url": "https://www.rrbbnc.gov.in/",
        "latest_news": "Application submitted Aug 31, 2026. CBT examination block calendar pending.",
    },
]

print(f"📥 [2/2] Populating {len(APPLIED_EXAMS)} applied exams into Notion...")

for item in APPLIED_EXAMS:
    props = {
        "Exam Name": {"title": [{"text": {"content": item["name"]}}]},
        "Authority": {"select": {"name": item["authority"]}},
        "Notification No": {"rich_text": [{"text": {"content": item["advt_no"]}}]},
        "Registration No": {"rich_text": [{"text": {"content": item["reg_no"]}}]},
        "Status": {"select": {"name": item["status"]}},
        "Exam Timeline": {"rich_text": [{"text": {"content": item["timeline"]}}]},
        "Notice Board URL": {"url": item["notice_url"]},
        "Latest News": {"rich_text": [{"text": {"content": item["latest_news"]}}]},
    }
    if item["exam_date"]:
        props["Exam Date"] = {"date": {"start": item["exam_date"]}}

    create_payload = {"parent": {"database_id": db_id}, "properties": props}
    resp = requests.post("https://api.notion.com/v1/pages", headers=headers, json=create_payload, timeout=30)
    if resp.status_code == 200:
        print(f"   ✅ Added: {item['name'][:45]}...")
    else:
        print(f"   ⚠️ Failed {item['name'][:30]}: {resp.text}")

print("\n🎉 All applied exams populated in Notion!")

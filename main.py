import os
import sys
import time
from playwright.sync_api import sync_playwright
from db import JobDatabase

# Windows console encoding safety
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

db = JobDatabase()

# Your target roles list
TARGET_ROLES = [
    "AI Engineer", 
    "ML Engineer", 
    "BI Engineer", 
    "Data Scientist", 
    "Data Analyst", 
    "AI/ML Engineer"
]

def run_job_bot():
    if not os.path.exists("state.json"):
        print("Error: state.json missing. Please run setup_auth.py first.")
        return

    with sync_playwright() as p:
        # headless=False so you can watch it perform the UI clicks
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()
        
        try:
            # Starts at the home feed
            page.goto("https://www.dice.com/home-feed", wait_until="domcontentloaded")
            time.sleep(3)

            # Iterate through each job role one by one
            for role in TARGET_ROLES:
                print(f"\n{'='*40}")
                print(f"🤖 SEARCHING FOR: {role}")
                print(f"{'='*40}")
                
                try:
                    # 1. Type in the top search bar
                    search_input = page.get_by_placeholder("Job title, skill, company")
                    search_input.fill(role)
                    search_input.press("Enter")
                    time.sleep(4) # Wait for initial results
                    
                    # 2. Click "All filters"
                    page.get_by_role("button", name="All filters").click()
                    time.sleep(2) # Wait for sidebar to slide out
                    
                    # 3. Check the "Easy Apply" box
                    page.locator("label").filter(has_text="Easy Apply").click()
                    time.sleep(1)
                    
                    # 4. Click "Apply filters" button at the bottom
                    page.get_by_role("button", name="Apply filters").click()
                    time.sleep(4) # Wait for the filtered job list to refresh
                    
                except Exception as e:
                    print(f"UI Navigation failed. Dice may have changed their layout: {e}")
                    continue # Skip to the next role if the UI breaks

                # --- GATHER PHASE ---
                job_cards = page.query_selector_all("dhi-search-card") or page.query_selector_all("[data-cy='search-card']")
                jobs_to_apply = []
                seen_ids = set()
                
                for card in job_cards:
                    try:
                        title_element = card.query_selector("a.card-title-link") or card.query_selector("a[data-cy='card-title-link']") or card.query_selector("a")
                        if not title_element:
                            continue
                        
                        raw_href = title_element.get_attribute("href") or ""
                        job_url = raw_href if raw_href.startswith("http") else f"https://www.dice.com{raw_href}"
                        job_title = title_element.inner_text().strip()
                        job_id = job_url.rstrip('/').split('/')[-1].split('?')[0]
                        
                        if job_id and job_id not in seen_ids:
                            seen_ids.add(job_id)
                            if not db.is_job_applied(job_id):
                                jobs_to_apply.append({"id": job_id, "title": job_title, "url": job_url})
                    except Exception:
                        continue # Silently skip broken cards

                print(f"Found {len(jobs_to_apply)} new {role} jobs. Applying now...")

                # --- APPLICATION PHASE ---
                for job in jobs_to_apply:
                    print(f"Processing: {job['title']} (ID: {job['id']})")
                    
                    try:
                        page.goto(job['url'], wait_until="domcontentloaded")
                        time.sleep(3)
                        
                        # 5. Click the blue Easy Apply button on the job page
                        apply_button = page.get_by_role("button", name="Easy Apply").first
                        if not apply_button.is_visible():
                            apply_button = page.locator("button:has-text('Easy Apply')").first
                        
                        if apply_button.is_visible():
                            apply_button.click()
                            time.sleep(2)
                            
                            step = 0
                            max_steps = 5
                            
                            # Form progression loop
                            while step < max_steps:
                                submit_btn = page.get_by_role("button", name="Submit").first
                                if not submit_btn.is_visible():
                                    submit_btn = page.locator("button:has-text('Submit Application')").first

                                next_btn = page.get_by_role("button", name="Next").first
                                if not next_btn.is_visible():
                                    next_btn = page.locator("button:has-text('Next')").first
                                
                                # 6. Click Submit or Next
                                if submit_btn.is_visible():
                                    submit_btn.click()
                                    db.record_job(job['id'], job['title'], "Unknown", job['url'], status="APPLIED")
                                    print(" -> SUCCESS: Application Submitted!")
                                    break
                                elif next_btn.is_visible():
                                    if next_btn.is_disabled():
                                        db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes="Next button disabled")
                                        print(" -> Failed: Form requires mandatory input.")
                                        break
                                    next_btn.click()
                                    time.sleep(2)
                                    step += 1
                                else:
                                    db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes="Stuck on custom questions")
                                    print(" -> Failed: Form requires manual text input.")
                                    break
                        else:
                            print(" -> Failed: Easy Apply button not found.")
                            db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes="No Easy Apply button")

                    except Exception as e:
                        print(f" -> Crash during application: {e}")
                        db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes=f"Error: {str(e)}")
                
                print(f"Finished {role}. Cooling down before next search...")
                time.sleep(5)
                
                # Navigate back to the home feed to reset the search bar for the next role
                page.goto("https://www.dice.com/home-feed", wait_until="domcontentloaded")
                time.sleep(3)

            print("\nAll roles processed! Closing browser.")
        finally:
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    run_job_bot()

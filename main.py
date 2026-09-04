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
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        try:
            for role in TARGET_ROLES:
                print(f"\n{'='*40}")
                print(f"🤖 SEARCHING FOR: {role}")
                print(f"{'='*40}")
                
                try:
                    page.goto("https://www.dice.com/home-feed", wait_until="domcontentloaded")
                    time.sleep(3)
                
                    # Search and Filter sequence
                    search_input = page.get_by_placeholder("Job title, skill, company")
                    search_input.fill(role)
                    search_input.press("Enter")
                    time.sleep(4) 
                    
                    page.get_by_role("button", name="All filters").click()
                    time.sleep(2) 
                    page.locator("label").filter(has_text="Easy Apply").click()
                    time.sleep(1)
                    page.get_by_role("button", name="Apply filters").click()
                    time.sleep(4) 
                    
                except Exception as e:
                    print(f"Failed to load search for {role}: {e}")
                    continue

                # PAGINATION LOOP: Will run until the last page is reached
                page_number = 1
                while True:
                    print(f"\n--- Scanning Page {page_number} for {role} ---")
                    
                    # SAVE THE SEARCH STATE: This acts as our safe "Go Back" mechanism
                    current_search_url = page.url 
                    
                    # Scroll down naturally to load all elements
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    # 1. GATHER ALL JOBS ON THIS PAGE
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
                            
                            # Requirement 3: Skip already applied jobs instantly
                            if not db.is_job_applied(job_id):
                                if job_id not in seen_ids:
                                    seen_ids.add(job_id)
                                    jobs_to_apply.append({"id": job_id, "title": job_title, "url": job_url})
                            else:
                                print(f"Skipping: {job_title} (Already Applied)")
                        except Exception:
                            continue

                    # Fallback via direct job-detail links
                    if not jobs_to_apply:
                        job_links = page.query_selector_all("a[href*='/job-detail/']")
                        for link in job_links:
                            try:
                                raw_href = link.get_attribute("href") or ""
                                job_url = raw_href if raw_href.startswith("http") else f"https://www.dice.com{raw_href}"
                                job_title = link.inner_text().strip()
                                if not job_title or len(job_title) < 3:
                                    continue
                                job_id = job_url.rstrip('/').split('/')[-1].split('?')[0]
                                if not db.is_job_applied(job_id):
                                    if job_id not in seen_ids:
                                        seen_ids.add(job_id)
                                        jobs_to_apply.append({"id": job_id, "title": job_title, "url": job_url})
                                else:
                                    print(f"Skipping: {job_title} (Already Applied)")
                            except Exception:
                                pass

                    print(f"Found {len(jobs_to_apply)} new jobs to process on this page.")

                    # 2. APPLY TO JOBS ONE BY ONE
                    for job in jobs_to_apply:
                        print(f"Processing: {job['title']} (ID: {job['id']})")
                        try:
                            page.goto(job['url'], wait_until="domcontentloaded")
                            time.sleep(3)
                            
                            apply_button = page.get_by_role("button", name="Easy Apply").first
                            if not apply_button.is_visible():
                                apply_button = page.locator("button:has-text('Easy Apply')").first
                            
                            if apply_button.is_visible():
                                apply_button.click()
                                time.sleep(2)
                                
                                step = 0
                                max_steps = 5
                                
                                # Form Flow: Next -> Next -> Submit
                                while step < max_steps:
                                    submit_btn = page.get_by_role("button", name="Submit").first
                                    if not submit_btn.is_visible():
                                        submit_btn = page.locator("button:has-text('Submit Application')").first

                                    next_btn = page.get_by_role("button", name="Next").first
                                    if not next_btn.is_visible():
                                        next_btn = page.locator("button:has-text('Next')").first
                                    
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
                                db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes="No Easy Apply button")
                                print(" -> Failed: Easy Apply button not found.")
                        except Exception as e:
                            print(f" -> Crash during application: {e}")
                            db.record_job(job['id'], job['title'], "Unknown", job['url'], status="FAILED", notes=f"Error: {str(e)}")
                        
                        # GO BACK: Reloads the search page exactly as it was, safely.
                        try:
                            page.goto(current_search_url, wait_until="domcontentloaded")
                            time.sleep(3)
                        except Exception as e:
                            print(f"Warning: Could not reload search URL: {e}")

                    # 3. TURN THE PAGE
                    # Looking for the Next page button (usually an arrow or 'Next' text)
                    next_button = page.locator("a[aria-label='Next'], li.pagination-next a, [data-cy='pagination-next']").first
                    
                    if next_button.is_visible() and not next_button.is_disabled():
                        print("Moving to the next page of search results...")
                        
                        # Scroll to bottom to ensure the Next button is in view
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                        
                        next_button.click()
                        page_number += 1
                        time.sleep(4) # Wait for next page to load
                    else:
                        print(f"Reached the final page for {role}.")
                        break # Break the while loop and move to the next TARGET_ROLE

            print("\nAll roles processed! Closing browser.")
        finally:
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    run_job_bot()

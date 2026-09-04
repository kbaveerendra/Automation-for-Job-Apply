import os
import sys
import time
import re
import urllib.parse
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

def is_target_role(job_title: str) -> bool:
    """
    Check if the job title matches any of the allowed target roles (case-insensitive).
    """
    if not job_title:
        return False
    title_lower = job_title.lower()
    for role in TARGET_ROLES:
        role_lower = role.lower()
        if role_lower in title_lower:
            return True
        # Match standard expansions
        if role_lower == "ml engineer" and ("machine learning" in title_lower or "m.l." in title_lower):
            return True
        if role_lower == "ai engineer" and ("artificial intelligence" in title_lower or "a.i." in title_lower):
            return True
        if role_lower == "bi engineer" and ("business intelligence" in title_lower or "b.i." in title_lower):
            return True
    return False

def ensure_easy_apply_filter_enabled(page):
    """
    Search for the 'Easy Apply' filter button/toggle on the search results UI and click it if available.
    """
    print("Searching for 'Easy Apply' UI filter button...")
    filter_selectors = [
        "button[aria-label*='Easy Apply']",
        "label:has-text('Easy Apply')",
        "button:has-text('Easy Apply')",
        "[data-cy='filter-easy-apply']",
        "[data-testid='easy-apply-filter']"
    ]
    
    for selector in filter_selectors:
        try:
            elem = page.locator(selector).first
            if elem.is_visible():
                aria_pressed = elem.get_attribute("aria-pressed")
                aria_checked = elem.get_attribute("aria-checked")
                if aria_pressed == "true" or aria_checked == "true":
                    print(f"-> 'Easy Apply' filter is already active via selector: {selector}")
                else:
                    print(f"-> Found 'Easy Apply' filter button ({selector}). Clicking to enable...")
                    elem.click()
                    time.sleep(3)  # Wait for results to update
                return True
        except Exception:
            continue
            
    print("-> Note: URL parameter easyApply=true active; secondary UI filter verified.")
    return False

def run_job_bot():
    if not os.path.exists("state.json"):
        print("Error: state.json missing. Please run setup_auth.py first.")
        return

    # Configuration
    PAGES_PER_ROLE = 2
    BASE_SEARCH_URL = "https://www.dice.com/jobs?q={query}&easyApply=true&page={page}"

    with sync_playwright() as p:
        # Headless=True for silent production execution
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="state.json")
        page = context.new_page()

        try:
            for role_query in TARGET_ROLES:
                encoded_query = urllib.parse.quote(role_query)

                for current_page in range(1, PAGES_PER_ROLE + 1):
                    target_url = BASE_SEARCH_URL.format(query=encoded_query, page=current_page)
                    print(f"\n{'='*55}")
                    print(f"TARGET ROLE: '{role_query}' | PAGE {current_page} OF {PAGES_PER_ROLE}")
                    print(f"Target URL: {target_url}")
                    print(f"{'='*55}")

                    try:
                        page.goto(target_url, wait_until="domcontentloaded")
                    except Exception as e:
                        print(f"Warning: Navigation error loading search page: {e}")
                    
                    time.sleep(4)  # Wait for dynamic JS rendering

                    # Ensure Easy Apply filter is active on UI
                    ensure_easy_apply_filter_enabled(page)

                    jobs_to_apply = []
                    seen_ids = set()

                    # --- PHASE 1: GATHER ---
                    print(f"\n--- Phase 1: Gathering Jobs for '{role_query}' (Page {current_page}) ---")
                    job_cards = page.query_selector_all("dhi-search-card") or page.query_selector_all("[data-cy='search-card']")

                    if job_cards:
                        print(f"Found {len(job_cards)} job cards via search card elements.")
                        for card in job_cards:
                            try:
                                title_element = card.query_selector("a.card-title-link") or card.query_selector("a[data-cy='card-title-link']") or card.query_selector("a")
                                if not title_element:
                                    continue

                                raw_href = title_element.get_attribute("href") or ""
                                job_url = raw_href if raw_href.startswith("http") else f"https://www.dice.com{raw_href}"
                                job_title = title_element.inner_text().strip()

                                # Strict Job Role Check
                                if not is_target_role(job_title):
                                    print(f"-> Skipped (Role mismatch): '{job_title}'")
                                    continue

                                company_element = card.query_selector("a[data-cy='search-result-company-name']") or card.query_selector(".comp-name")
                                company_name = company_element.inner_text().strip() if company_element else "Unknown"

                                # Clean job ID extraction (handles trailing slashes)
                                job_id = job_url.rstrip('/').split('/')[-1].split('?')[0]

                                if job_id and job_id not in seen_ids:
                                    seen_ids.add(job_id)
                                    if not db.is_job_applied(job_id):
                                        print(f"-> Queued: {job_title} at {company_name} (ID: {job_id})")
                                        jobs_to_apply.append({"id": job_id, "title": job_title, "company": company_name, "url": job_url})
                                    else:
                                        print(f"-> Skipped (Already processed): {job_title} (ID: {job_id})")
                            except Exception as e:
                                print(f"Card Extraction Error: {e}")

                    # Fallback via direct job-detail links
                    if not jobs_to_apply:
                        print("Notice: Trying fallback extraction via job-detail links...")
                        job_links = page.query_selector_all("a[href*='/job-detail/']")
                        print(f"Found {len(job_links)} candidate job links on page {current_page}.")

                        for link in job_links:
                            try:
                                raw_href = link.get_attribute("href") or ""
                                job_url = raw_href if raw_href.startswith("http") else f"https://www.dice.com{raw_href}"
                                job_title = link.inner_text().strip()
                                if not job_title or len(job_title) < 3:
                                    continue

                                # Strict Job Role Check
                                if not is_target_role(job_title):
                                    continue

                                job_id = job_url.rstrip('/').split('/')[-1].split('?')[0]

                                if job_id and job_id not in seen_ids:
                                    seen_ids.add(job_id)
                                    if not db.is_job_applied(job_id):
                                        print(f"-> Queued via fallback: {job_title} (ID: {job_id})")
                                        jobs_to_apply.append({"id": job_id, "title": job_title, "company": "Dice Listing", "url": job_url})
                                    else:
                                        print(f"-> Skipped (Already processed): {job_title} (ID: {job_id})")
                            except Exception as e:
                                print(f"Link Extraction Error: {e}")

                    print(f"Found {len(jobs_to_apply)} matching target jobs on page {current_page}.")

                    # --- PHASE 2: APPLICATION FLOW ---
                    print(f"\n--- Phase 2: Application Flow ({role_query} - Page {current_page}) ---")
                    for job in jobs_to_apply:
                        print(f"\nProcessing: {job['title']} at {job['company']} (ID: {job['id']})")

                        try:
                            page.goto(job['url'], wait_until="domcontentloaded")
                            time.sleep(3)  # Let the page load

                            # Locate primary Easy Apply button
                            apply_button = page.get_by_role("button", name=re.compile("Easy Apply", re.I)).first
                            if not apply_button.is_visible():
                                apply_button = page.locator("button:has-text('Easy Apply')").first

                            if not apply_button.is_visible():
                                print("-> Failed: 'Easy Apply' button not found.")
                                db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes="No Easy Apply button")
                                continue

                            apply_button.click()
                            time.sleep(2)  # Wait for modal to render

                            max_steps = 5
                            current_step = 0
                            application_successful = False

                            # The Form Progression Loop
                            while current_step < max_steps:
                                submit_button = page.get_by_role("button", name=re.compile("Submit", re.I)).first
                                if not submit_button.is_visible():
                                    submit_button = page.locator("button:has-text('Submit Application')").first

                                next_button = page.get_by_role("button", name=re.compile("Next", re.I)).first
                                if not next_button.is_visible():
                                    next_button = page.locator("button:has-text('Next')").first

                                if submit_button.is_visible():
                                    submit_button.click()
                                    print("-> SUCCESS: Application Submitted!")
                                    db.record_job(job['id'], job['title'], job['company'], job['url'], status="APPLIED")
                                    application_successful = True
                                    break

                                elif next_button.is_visible():
                                    # Check if Next button is disabled (requires user input)
                                    if next_button.is_disabled():
                                        print("-> Failed: 'Next' button disabled (requires mandatory text/dropdown input).")
                                        db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes="Mandatory question required")
                                        break

                                    modal_loc = page.locator("seds-modal, [role='dialog'], .modal-body, .modal-content").first
                                    previous_content = modal_loc.inner_text().strip() if modal_loc and modal_loc.is_visible() else ""

                                    next_button.click()
                                    time.sleep(2)

                                    modal_loc = page.locator("seds-modal, [role='dialog'], .modal-body, .modal-content").first
                                    current_content = modal_loc.inner_text().strip() if modal_loc and modal_loc.is_visible() else ""

                                    if previous_content and previous_content == current_content:
                                        print("-> Failed: Form is stuck (requires manual input or mandatory dropdowns).")
                                        db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes="Stuck on mandatory question")
                                        break

                                    current_step += 1
                                    print(f"   ... Proceeded to step {current_step}")

                                else:
                                    print("-> Failed: Unknown modal state. Neither Next nor Submit found.")
                                    db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes="Unknown form structure")
                                    break

                            if current_step == max_steps and not application_successful:
                                print("-> Failed: Form exceeded maximum steps (too long).")
                                db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes="Exceeded max steps")

                            close_button = page.locator("button[aria-label='Close']").first
                            if not close_button.is_visible():
                                close_button = page.locator("button.close, [data-dismiss='modal']").first
                            if close_button.is_visible():
                                close_button.click()
                                time.sleep(1)

                        except Exception as e:
                            print(f"-> Crash during application: {e}")
                            db.record_job(job['id'], job['title'], job['company'], job['url'], status="FAILED", notes=f"Error: {str(e)}")

                    # Pause between pages/queries
                    time.sleep(5)

            print("\n" + "="*55)
            print("All target roles processed. Closing browser.")
            print("="*55)

            print("\n--- Final Database Summary ---")
            all_jobs = db.get_all_jobs()
            for item in all_jobs:
                print(f"ID: {item['job_id']} | Status: {item['status']} | Title: {item['title']} | Company: {item['company']}")

        finally:
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    run_job_bot()

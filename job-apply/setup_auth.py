import sys
from playwright.sync_api import sync_playwright

# Windows console encoding safety
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def save_dice_session():
    with sync_playwright() as p:
        # headless=False is required so you can see the screen to type your credentials
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto("https://www.dice.com/dashboard/login", wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation note: {e}")

        print("=" * 60)
        print("Browser opened. Please log in to your Dice account manually.")
        print("Once logged in, return to this terminal and press ENTER to save session.")
        print("=" * 60)
        
        try:
            input("\n--> Press ENTER here after you complete login: ")
            context.storage_state(path="state.json")
            print("\nSession saved successfully to state.json!")
        except Exception as e:
            print(f"\nCould not save session state: {e}")
        finally:
            try:
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    save_dice_session()

import time
import json
import os
import random
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import pandas as pd
import psutil
import tempfile

# ----------------------- CONFIGURATION ---------------------------------------
output_folder = "donations_data"
campaign = "luigi-defense-fund"
checkpoint_file = os.path.join(output_folder, "checkpoint.json")
csv_file = os.path.join(output_folder, "all_donations.csv")
max_pages_initial = 5000  # For full initial scrape
max_pages_update = 100    # For incremental updates
base_url = f"https://www.givesendgo.com/api/v2/campaigns/{campaign}/get-recent-donations?pageNo={{}}"

# Create output folder
os.makedirs(output_folder, exist_ok=True)

# Load checkpoint (if exists)
if os.path.exists(checkpoint_file):
    with open(checkpoint_file, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)
        all_donations = checkpoint.get("donations", [])
        last_page = checkpoint.get("last_page", 0)
        last_donation_id = checkpoint.get("last_donation_id", None)
        newest_donation_id = checkpoint.get("newest_donation_id", None)
        initial_scrape_complete = checkpoint.get("initial_scrape_complete", False)
else:
    all_donations = []
    last_page = 0
    last_donation_id = None
    newest_donation_id = None
    initial_scrape_complete = False

print(f"Initial scrape complete: {initial_scrape_complete}")
print(f"Currently have {len(all_donations)} donations in memory")

# Check for stop file
def check_stop_signal():
    return os.path.exists(os.path.join(output_folder, "stop.txt"))

# Terminate existing chromedriver processes
def kill_chromedriver_processes():
    print("Terminating any existing chromedriver processes...")
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == 'chromedriver.exe':
            try:
                proc.terminate()
                proc.wait(timeout=3)
                print(f"Terminated chromedriver process with PID {proc.pid}")
            except psutil.NoSuchProcess:
                pass
            except psutil.TimeoutExpired:
                proc.kill()
                print(f"Forced termination of chromedriver process with PID {proc.pid}")

# ----------------------- SCRAPING FUNCTION -----------------------------------
def fetch_page(driver, page, retries=3):
    url = base_url.format(page)
    for attempt in range(retries):
        try:
            driver.get(url)
            time.sleep(random.uniform(0.4, 0.8))
            page_source = driver.page_source
            if "Just a moment..." in page_source:
                print(f"Cloudflare challenge detected on page {page}, attempt {attempt + 1}")
                if attempt == retries - 1:
                    print(f"Cloudflare block after {retries} attempts on page {page}. Pausing for manual resolution...")
                    input("Press Enter after resolving Cloudflare CAPTCHA in the browser...")
                    return page, None, None
                time.sleep(3)
                continue
            soup = BeautifulSoup(page_source, "html.parser")
            pre = soup.find("pre")
            if not pre:
                print(f"No JSON found on page {page}, attempt {attempt + 1}")
                if attempt == retries - 1:
                    print(f"No JSON after {retries} attempts on page {page}")
                    return page, None, None
                time.sleep(2)
                continue
            try:
                data = json.loads(pre.text.strip())
                donations = data.get("returnData", {}).get("donations", [])
                return page, donations, data
            except json.JSONDecodeError as e:
                print(f"JSON parse error on page {page}, attempt {attempt + 1}: {e}")
                if attempt == retries - 1:
                    print(f"JSON parse failed after {retries} attempts on page {page}")
                    return page, None, None
                time.sleep(2)
        except Exception as e:
            print(f"Error on page {page}, attempt {attempt + 1}: {e}")
            if attempt == retries - 1:
                print(f"Failed after {retries} attempts on page {page}")
                return page, None, None
            time.sleep(2)
    return page, None, None

def scrape_all_donations():
    """Scrape ALL donations (initial full scrape)"""
    global all_donations, last_donation_id, newest_donation_id
    
    print("STARTING FULL INITIAL SCRAPE...")
    print(f"Scraping all donations from page 0 to {max_pages_initial - 1}")
    
    start_page = 0
    end_page = max_pages_initial - 1
    
    print(f"Initializing Chrome browser...")
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument(f"--user-data-dir={tempfile.gettempdir()}/chrome_profile_single")   
    driver = None
    total_new_donations = 0
    
    try:
        driver = uc.Chrome(options=options)
        print("Chrome initialized successfully.")
        
        current_page = start_page
        
        while current_page <= end_page and not check_stop_signal():
            print(f"Processing page {current_page}...")
            
            page, donations, data = fetch_page(driver, current_page)
            
            if donations is None:
                print(f"Skipping page {current_page} due to failures")
                current_page += 1
                continue
            
            if not donations:
                print(f"No donations on page {current_page}, stopping early")
                break
            
            # Add ALL donations (no filtering for initial scrape)
            all_donations = donations + all_donations
            total_new_donations += len(donations)
            
            # Save individual page JSON
            filename = os.path.join(output_folder, f"donations_page{current_page}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"✓ Page {current_page}: Added {len(donations)} donations")
            
            # Save checkpoint every 10 pages
            if current_page % 10 == 0:
                checkpoint = {
                    "donations": all_donations,
                    "last_page": current_page,
                    "last_donation_id": all_donations[-1].get("donation_id") if all_donations else None,
                    "newest_donation_id": all_donations[0].get("donation_id") if all_donations else None,
                    "initial_scrape_complete": False
                }
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                print(f"Checkpoint saved at page {current_page}: {len(all_donations)} total donations")
            
            current_page += 1
        
        # Mark initial scrape as complete
        if all_donations:
            newest_donation_id = all_donations[0].get("donation_id")
            last_donation_id = all_donations[-1].get("donation_id")
            print(f"✅ Initial scrape complete! Newest donation ID: {newest_donation_id}")
        
        return total_new_donations
        
    except Exception as e:
        print(f"Error during full scrape: {e}")
        return total_new_donations
    finally:
        if driver:
            try:
                driver.quit()
                print("Browser closed successfully.")
            except Exception as e:
                print(f"Warning during browser cleanup: {e}")

def scrape_new_donations():
    """Scrape only NEW donations (incremental update)"""
    global all_donations, last_donation_id, newest_donation_id
    
    print("CHECKING FOR NEW DONATIONS...")
    
    start_page = 0
    end_page = max_pages_update - 1
    
    print(f"Initializing Chrome browser...")
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    options.add_argument(f"--user-data-dir={tempfile.gettempdir()}/chrome_profile_single")
    
    driver = None
    new_donations_count = 0
    
    try:
        driver = uc.Chrome(options=options)
        print("Chrome initialized successfully.")
        
        current_page = start_page
        consecutive_known_pages = 0
        
        while current_page <= end_page and not check_stop_signal():
            print(f"Checking page {current_page} for new donations...")
            
            page, donations, data = fetch_page(driver, current_page)
            
            if donations is None:
                print(f"Skipping page {current_page} due to failures")
                current_page += 1
                continue
            
            if not donations:
                print(f"No donations on page {current_page}, stopping")
                break
            
            # Filter for only NEW donations using donation_id
            new_donations_on_page = []
            existing_ids = {d.get("donation_id") for d in all_donations}
            
            for donation in donations:
                donation_id = donation.get("donation_id")
                
                if donation_id not in existing_ids:
                    new_donations_on_page.append(donation)
                    print(f"Found new donation: {donation_id}")
            
            if new_donations_on_page:
                # Add new donations to the BEGINNING
                all_donations = new_donations_on_page + all_donations
                new_donations_count += len(new_donations_on_page)
                consecutive_known_pages = 0  # Reset counter when we find new donations
                
                print(f"✓ Page {current_page}: Added {len(new_donations_on_page)} new donations")
            else:
                print(f"Page {current_page}: No new donations found (all {len(donations)} donations already known)")
                consecutive_known_pages += 1
                
                # Stop if we've seen 3 consecutive pages with no new donations
                if consecutive_known_pages >= 3:
                    print(f"Stopping after {consecutive_known_pages} consecutive pages with no new donations")
                    break
            
            current_page += 1
        
        return new_donations_count
        
    except Exception as e:
        print(f"Error during incremental scrape: {e}")
        return new_donations_count
    finally:
        if driver:
            try:
                driver.quit()
                print("Browser closed successfully.")
            except Exception as e:
                print(f"Warning during browser cleanup: {e}")

# ----------------------- CSV GENERATION FUNCTION -----------------------------
def generate_csv():
    """Generate CSV file from collected data"""
    print("Generating CSV file from collected data...")
    
    if all_donations:
        df = pd.DataFrame(all_donations)
        
        # Remove duplicates based on donation_id
        initial_count = len(df)
        df = df.drop_duplicates(subset=["donation_id"], keep="first")
        final_count = len(df)
        
        if initial_count != final_count:
            print(f"Removed {initial_count - final_count} duplicate donations")
        
        # Replace empty donation names with "Anonymous"
        if 'donation_name' in df.columns:
            # Count empty names before replacement
            empty_names_before = df['donation_name'].isna() | (df['donation_name'] == '')
            empty_count = empty_names_before.sum()
            
            # Replace empty names with "Anonymous"
            df['donation_name'] = df['donation_name'].fillna('Anonymous')
            df.loc[df['donation_name'] == '', 'donation_name'] = 'Anonymous'
            
            # Count after replacement to confirm
            empty_names_after = (df['donation_name'] == 'Anonymous').sum()
            
            if empty_count > 0:
                print(f"✓ Replaced {empty_count} empty donation names with 'Anonymous'")
        
        # Remove unwanted columns
        columns_to_remove = [
            "donation_comment_reply", 
            "donation_conversion_rate", 
            "donation_amount_actual", 
            "donation_date", 
            "likes"
        ]
        
        # Only remove columns that exist in the dataframe
        existing_columns_to_remove = [col for col in columns_to_remove if col in df.columns]
        if existing_columns_to_remove:
            df = df.drop(columns=existing_columns_to_remove)
            print(f"Removed columns: {', '.join(existing_columns_to_remove)}")
        
        df.to_csv(csv_file, index=False, encoding="utf-8-sig")
        print(f"✓ CSV file generated: {csv_file}")
        print(f"✓ Total donations saved: {len(df)}")
        print(f"✓ Remaining columns: {', '.join(df.columns.tolist())}")
        
        return len(df)
    else:
        print("✗ No donations data found to save to CSV")
        return 0

# ----------------------- MAIN EXECUTION --------------------------------------
def main():
    global all_donations, last_donation_id, newest_donation_id, initial_scrape_complete

    # Terminate any existing chromedriver processes
    kill_chromedriver_processes()

    # Pre-initialize undetected_chromedriver
    print("Pre-initializing undetected_chromedriver...")
    try:
        driver = uc.Chrome()
        driver.quit()
        print("Pre-initialization complete.")
    except Exception as e:
        print(f"Pre-initialization warning: {e}")

    try:
        if not initial_scrape_complete:
            # DO FULL INITIAL SCRAPE
            print("INITIAL SCRAPE MODE: Getting ALL donations...")
            new_donations_count = scrape_all_donations()
            
            if new_donations_count > 0:
                print(f"Initial scrape complete! Found {new_donations_count} total donations!")
                
                # Mark initial scrape as complete
                initial_scrape_complete = True
                checkpoint = {
                    "donations": all_donations,
                    "last_page": 0,
                    "last_donation_id": all_donations[-1].get("donation_id") if all_donations else None,
                    "newest_donation_id": all_donations[0].get("donation_id") if all_donations else None,
                    "initial_scrape_complete": True
                }
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                print(f"✅ Initial scrape marked as complete. Total donations: {len(all_donations)}")
            else:
                print("❌ Initial scrape failed or found no donations")
        
        else:
            # DO INCREMENTAL UPDATE
            print("INCREMENTAL UPDATE MODE: Checking for NEW donations only...")
            new_donations_count = scrape_new_donations()
            
            if new_donations_count > 0:
                print(f"Found {new_donations_count} NEW donations!")
                
                # Update checkpoint
                checkpoint = {
                    "donations": all_donations,
                    "last_page": 0,
                    "last_donation_id": all_donations[-1].get("donation_id") if all_donations else None,
                    "newest_donation_id": all_donations[0].get("donation_id") if all_donations else None,
                    "initial_scrape_complete": True
                }
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                print(f"Checkpoint updated with {len(all_donations)} total donations")
            else:
                print("✅ No new donations found - you're up to date!")
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        print("Continuing with CSV generation...")
    
    # Always generate CSV at the end
    donation_count = generate_csv()
    print(f"Script completed. Total donations: {donation_count}")

# Run the script
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript interrupted by user. Saving data...")
        generate_csv()
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Attempting to generate CSV with available data...")
        generate_csv()
import requests
from bs4 import BeautifulSoup
import re
import csv
from io import StringIO, BytesIO
from urllib.parse import urljoin, urlparse
import time
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests.exceptions import RequestException, SSLError, HTTPError, ConnectionError
from urllib3.exceptions import MaxRetryError, NewConnectionError
import streamlit as st

# Suppress only the single InsecureRequestWarning from urllib3 needed to silence the warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Function to validate and filter phone numbers
def is_valid_phone(phone):
    # Adjusted regex pattern to match various phone number formats, including extensions
    phone_pattern = re.compile(r'(\+?\d{1,2}\s?)?(\(?\d{3}\)?|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?:\s?(?:ext|x|ext.)\s?\d{1,5})?')
    return phone_pattern.match(phone) is not None

# Function to get all links from a given URL
def get_all_links_from_url(url, session):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'}
    try:
        response = session.get(url, timeout=10, verify=False, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('/'):
                href = urljoin(base_url, href)
            if href.startswith('http') and base_url in href:
                links.add(href)
        return links
    except (RequestException, MaxRetryError, NewConnectionError, SSLError, HTTPError, ConnectionError) as e:
        print(f"Error fetching links from {url}: {e}")
        return set()

# Function to get phone numbers from specific pages like "contact us", "about us"
def get_contact_info_from_specific_pages(base_url, links, session, unique_phones):
    target_pages = ['contact', 'about', 'get-in-touch', 'contact-us', 'about-us']
    contacts = []
    for link in links:
        for target in target_pages:
            if target in link.lower():
                found_contacts = get_contact_info_from_url(link, session, unique_phones)
                contacts.extend(found_contacts)
                break
        try:
            response = session.get(link, timeout=10, verify=False)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text().lower()
            for target in target_pages:
                if target in text:
                    found_contacts = get_contact_info_from_url(link, session, unique_phones)
                    contacts.extend(found_contacts)
                    break
        except Exception as e:
            print(f"Error parsing {link}: {e}")
    return contacts

def get_contact_info_from_url(url, session, unique_phones):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36'}
    try:
        response = session.get(url, timeout=10, verify=False, headers=headers)
        response.raise_for_status()

        phones = re.findall(r'(\+?\d{1,2}\s?)?(\(?\d{3}\)?|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?:\s?(?:ext|x|ext.)\s?\d{1,5})?', response.text)
        valid_phones = [phone[0] for phone in phones if is_valid_phone(phone[0]) and phone[0] not in unique_phones]
        unique_phones.update(valid_phones)

        return [(url, phone, 'phone') for phone in valid_phones]
    except (RequestException, MaxRetryError, NewConnectionError, SSLError, HTTPError, ConnectionError) as e:
        print(f"Error fetching contact info from {url}: {e}")
        return []

# Main scraping function
def scrape_contact_info(urls):
    contact_data = []
    visited_urls = set()
    unique_phones = set()
    start_time = time.time()
    max_time = 240  # Maximum time to spend on scraping in seconds

    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    for url in urls:
        if time.time() - start_time > max_time:
            break

        if not url.startswith('http'):
            url = 'http://' + url

        # Visit each URL and search for emails and phone numbers
        base_url = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))
        contacts = get_contact_info_from_url(url, session, unique_phones)
        if contacts:
            for contact in contacts:
                if contact not in contact_data:
                    contact_data.append(contact)

        visited_urls.add(url)

        all_links = get_all_links_from_url(url, session)
        target_contacts = get_contact_info_from_specific_pages(base_url, all_links, session, unique_phones)
        for contact in target_contacts:
            if contact not in contact_data:
                contact_data.append(contact)

        for link in all_links:
            if time.time() - start_time > max_time:
                break
            if link not in visited_urls:
                contacts = get_contact_info_from_url(link, session, unique_phones)
                if contacts:
                    for contact in contacts:
                        if contact not in contact_data:
                            contact_data.append(contact)
                visited_urls.add(link)

    return contact_data

# Function to save contact information to CSV
def save_contact_info_to_csv(contact_data):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Website', 'Contact', 'Type'])
    for url, contact, contact_type in contact_data:
        writer.writerow([url, contact, contact_type])
    output.seek(0)
    csv_binary = BytesIO(output.getvalue().encode('utf-8'))
    return csv_binary

# Streamlit app
def main():
    st.title('Contact Info Scraper')
    st.write('Enter URLs to scrape for phone numbers:')

    urls_input = st.text_area('Enter one URL per line:')
    urls = [url.strip() for url in urls_input.split('\n') if url.strip()]

    if st.button('Scrape Contacts'):
        with st.spinner('Scraping contacts...'):
            contact_data = scrape_contact_info(urls)
            st.success('Scraping completed!')
            if contact_data:
                st.write('Contact info found:')
                for url, contact, contact_type in contact_data:
                    st.write(f'**{contact_type.capitalize()} from {url}:** {contact}')
                csv_data = save_contact_info_to_csv(contact_data)
                st.download_button(
                    label="Download CSV",
                    data=csv_data,
                    file_name='contact_info.csv',
                    mime='text/csv',
                )
            else:
                st.write('No contact info found.')

if __name__ == "__main__":
    main()

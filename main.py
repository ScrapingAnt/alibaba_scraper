import csv
import json
import base64
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt
import click

SUPPORTED_COUNTRIES = [
    'ae',  # United Arab Emirates (the)
    'br',  # Brasilia
    'cn',  # China
    'de',  # Germany
    'es',  # Spain
    'fr',  # France
    'gb',  # United Kingdom (the)
    'hk',  # Hong Kong
    'in',  # India
    'it',  # Italy
    'il',  # Israel
    'jp',  # Japan
    'nl',  # Netherlands (the)
    'ru',  # Russia
    'sa',  # Saudi Arabia
    'us',  # USA
]


def make_scrapingant_request(target_url, rapidapi_key, js_snippet=None, proxy_country=None):
    print(f'getting page {target_url}')
    headers = {
        'x-rapidapi-host': "scrapingant.p.rapidapi.com",
        'x-rapidapi-key': rapidapi_key,
    }
    request_data = {'url': target_url}
    if js_snippet:
        encoded_js_snippet = base64.b64encode(js_snippet.encode()).decode()
        request_data['js_snippet'] = encoded_js_snippet
    if proxy_country:
        request_data['proxy_country'] = proxy_country.lower()

    r = requests.post(
        'https://scrapingant.p.rapidapi.com/post',
        data=json.dumps(request_data),
        headers=headers
    )
    return r.text


def extract_data_from_html(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    items_elements = soup.find_all(attrs={'data-role': 'item'})
    items_data_list = []
    for item_element in items_elements:
        title_element = item_element.find(attrs={'class': ['organic-gallery-title__content', 'ic-offer__title-text']})
        if not title_element:
            continue
        item_data = {'listing_title': title_element.getText()}
        seller_element = item_element.find(attrs={'flasher-type': 'supplierName'})
        if seller_element:
            item_data['seller_name'] = seller_element.getText()
            item_data['store_url'] = seller_element['href'][2:]
        seller_country_element = item_element.find(attrs={'class': 'seller-tag__country'})
        if seller_country_element:
            item_data['seller_location'] = seller_country_element['title']
        image_element = item_element.find(attrs={"flasher-type": "mainImage"})
        if image_element:
            item_data['image_url'] = image_element['data-image'][2:]
        price_element = item_element.find(attrs={'class': ['gallery-offer-price', 'ic-offer-price']})
        if price_element:
            item_data['price'] = price_element.getText()
        link_element = item_element.find(attrs={'class': ['organic-gallery-title', 'ic-offer__title-link-wrapper']})
        if link_element:
            item_data['item_url'] = link_element['href'][2:]
        items_data_list.append(item_data)
    print(f'Got {len(items_data_list)} items')

    return items_data_list


@retry(stop=stop_after_attempt(3), retry_error_callback=lambda _: list())
def extract_items_from_url(url_string, rapidapi_key, country):
    js_snippet = """
    window.scrollTo(0,document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 5000));
    """  # scroll to the end of page and sleep 5 seconds to wait lazy load complete
    page_html = make_scrapingant_request(url_string, rapidapi_key, js_snippet=js_snippet, proxy_country=country)
    data = extract_data_from_html(page_html)
    assert data
    return data


def get_search_results(search_string, rapidapi_key, pages, country):
    search_params = urllib.parse.urlencode({'SearchText': search_string})
    search_url = f'https://www.alibaba.com/trade/search?{search_params}'
    items_list = extract_items_from_url(search_url, rapidapi_key, country)
    if items_list:
        for page in range(2, pages + 1):
            page_url = f'{search_url}&page={page}'
            new_items = extract_items_from_url(page_url, rapidapi_key, country)
            if not new_items:
                break
            items_list.extend(new_items)
    return items_list


@click.command()
@click.argument('search_string', type=str, required=True, )
@click.option("--rapidapi_key", type=str, required=True,
              help="""\b
              Api key from https://rapidapi.com/okami4kak/api/scrapingant""")
@click.option("--pages", type=int, default=2, help="Number of search pages to parse")
@click.option("--country", type=click.Choice(SUPPORTED_COUNTRIES, case_sensitive=False),
              default="us", help="Country of proxies location ")
def main(search_string, rapidapi_key, pages, country):
    results = get_search_results(search_string, rapidapi_key, pages, country)
    if results:
        header = ['item_url', 'listing_title', 'seller_name', 'store_url', 'price', 'image_url', 'seller_location']
        filename = f'data/{search_string}_{datetime.now()}.csv'
        Path("data/").mkdir(parents=True, exist_ok=True)
        with open(filename, "w", newline="") as f:
            cw = csv.DictWriter(f, header, delimiter='\t', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            cw.writeheader()
            cw.writerows(results)
        print(f'Data saved to {filename}')
    else:
        print('no items found')


if __name__ == '__main__':
    main()

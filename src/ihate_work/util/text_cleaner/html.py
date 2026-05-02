import re

import yaml
from bs4 import BeautifulSoup, NavigableString


def clean_html(html_content: str) -> str:
    # Create BeautifulSoup object
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, str) and "<!--" in text):
        comment.extract()

    # Remove all attributes from tags
    for tag in soup.find_all(True):
        tag.attrs = {}

    # Remove empty tags (no text content)
    def remove_empty_tags(soup_object):
        for tag in soup_object.find_all():
            # Check if tag has no text content (including nested content)
            if len(tag.get_text(strip=True)) == 0:
                tag.decompose()

    # Keep removing empty tags until no changes are made
    prev_len = len(str(soup))
    while True:
        remove_empty_tags(soup)
        current_len = len(str(soup))
        if current_len == prev_len:  # No more changes
            break
        prev_len = current_len

    # Get the cleaned HTML
    cleaned_html = soup.prettify()

    # Remove extra whitespace and empty lines
    cleaned_html = re.sub(r"\n\s*\n", "\n", cleaned_html)
    cleaned_html = re.sub(r"^\s+$", "", cleaned_html, flags=re.MULTILINE)
    return cleaned_html


def html_to_yaml(html_content):
    # Parse HTML using BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Function to extract text nodes recursively
    def extract_text_nodes(element: BeautifulSoup | NavigableString | str):
        result = []

        if isinstance(element, str):
            text = element.strip()
            if text:  # Only add non-empty strings
                result.append(text)
            return result

        # Handle NavigableString directly
        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text:
                result.append(text)
            return result

        # Recursively process child elements
        for child in element.children:
            result.append(extract_text_nodes(child))

        res = list(filter(None, result))
        if len(res) == 1:
            return res[0]  # Flatten list if only one element
        else:
            return res

    # Extract all text nodes
    text_nodes = extract_text_nodes(soup)

    # Convert to YAML format
    yaml_content = yaml.dump(text_nodes, allow_unicode=True)

    return yaml_content

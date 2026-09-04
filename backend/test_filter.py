from scraping.filters import filter_blog_urls
urls = [
    "https://circuitdiagrammaker.com/battery-circuit",
    "https://circuitdiagrammaker.com/battery-circuit-diagram",
    "https://circuitdiagrammaker.com/about-us",
    "https://circuitdiagrammaker.com/blog/how-to",
    "https://circuitdiagrammaker.com/tools/diagram"
]
print(filter_blog_urls(urls, None, "https://circuitdiagrammaker.com"))

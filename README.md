# 🚀 Poizon Scraper

Poizon Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Poizon data for free.

## ✨ What Can I Get?

- 👟 **Full details of 1.5M+ authenticated products** — every size's live price and delivery options, style code, release date, images, 3D model, specs, rating and fit advice
- 🔍 **Search 400+ global brands in 2 markets** — by name or style code, with 5 sorts and 9 filters, in Korea (KRW) or Russia (RUB)
- ⭐ **Every review, up to 266 on a single sneaker** — rating, text, date, size bought, fit, foot length, buyer badges and photos
- 🗂️ **9 categories & 67 subcategories** — sneakers, shoes, apparel, bags, accessories, toys, beauty, electronics and home, each listed with its products

## 👟 Example: A Full Poizon Sneaker

```json
{
  "id": 60672611,
  "title": "Nike Dunk Low 'Panda Black White'",
  "link": "https://kr.poizon.com/product/60672611",
  "style_code": "DD1391-100",
  "price": 126970,
  "highest_price": 187180,
  "currency": "KRW",
  "is_in_stock": true,
  "gender": "unisex",
  "release_date": "2021-08-18",
  "favorites_count": 3700000,
  "rating": 5.0,
  "review_count": 20,
  "fit_advice": "Runs small, consider 1 size up.",
  "brand": { "id": 144, "name": "Nike", "link": "https://kr.poizon.com/brand/nike", "product_count": 330000 },
  "category": { "id": 500000091, "name": "Sneakers", "link": "https://kr.poizon.com/category/sneakers" },
  "variants": [
    {
      "id": 879447332,
      "options": [{ "name": "Edition", "value": "Original Shoe Box Included" }, { "name": "Size", "value": "240 (US 6)" }],
      "price": 148500,
      "tags": ["Selling out"],
      "delivery_options": [{ "type": "Local", "min_days": 6, "max_days": 9, "price": 148500, "currency": "KRW", "is_free_shipping": false }]
    }
  ],
  "images": ["https://cdn.poizon.com/pro-img/origin-img/20251206/002d13339da643c9a095b9a2f32d0fb9.jpg"],
  "model_3d": { "cover": "https://3d-media.poizon.com/images/3d/20240531/2ec64436-d2f5-482a-9914-5813477b5af7.png" },
  "properties": [{ "name": "Upper Material", "value": "Leather", "group": "Key Details" }, { "name": "Colorway", "value": "White/Black", "group": "Additional Details" }],
  "dewu_product_id": 1237613
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Poizon Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/poizon-scraper
cd poizon-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

Your own connection is fine to start, with no proxy at all.

Running searches, category or brand lists back to back? POIZON gives one address a captcha for 10 minutes after 70 to 119 of those calls in a row. Set `POIZON_PROXY=http://user:pass@host:port` to a rotating datacenter proxy and keep going.

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=60672611"
```

```json
{
  "id": 60672611,
  "title": "Nike Dunk Low 'Panda Black White'",
  "link": "https://kr.poizon.com/product/60672611",
  "style_code": "DD1391-100",
  "price": 126970,
  "highest_price": 187180,
  "currency": "KRW",
  "is_in_stock": true,
  "size_system": "KR",
  "release_date": "2021-08-18",
  "favorites_count": 3700000,
  "rating": 5.0,
  "fit_advice": "Runs small, consider 1 size up.",
  "brand": { "id": 144, "name": "Nike", "link": "https://kr.poizon.com/brand/nike" },
  "variants": [
    { "id": 879447332, "title": "Nike Dunk Low 'Panda Black White' Original Shoe Box Included 240 (US 6)", "price": 148500, "currency": "KRW", "is_available": true }
  ]
}
```

All 7 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

7 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | One product in full: every size's price, delivery, specs, 3D model |
| Search Products | `/products/search` | Products by name or style code, with 5 sorts and 9 filters |
| Product Reviews | `/products/reviews` | Ratings, texts, sizes bought, fit and buyer photos |
| Similar Products | `/products/similar` | The products POIZON recommends next to any product |
| Brand Products / Category Products | `/brands/products`, `/categories/products` | Every product of a brand or category, with the same filters |
| Categories | `/categories/list` | 9 categories and 67 subcategories with their ids |

Titles and labels come in English or Korean (`language`). Review texts stay in the catalog's own language: Korean, or Russian with `region=ru`.

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-poizon-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-poizon-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-poizon-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/details",
    params={"product": "60672611"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Poizon Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/poizon-scraper-github-whatsapp)

[![Ask Us by Email about Poizon Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Poizon%20Scraper%20API&body=I%20need%20help%20using%20the%20Poizon%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/poizon-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/poizon-scraper)

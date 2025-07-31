from fastapi import FastAPI, HTTPException
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import re
from typing import Optional
import logging
from playwright.async_api import async_playwright

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# Placeholder for future politician mapping table
POLITICIAN_MAPPING = {
    "Nancy Pelosi": "P000197"
}

# Helper function to clean text
def clean_text(text: str) -> str:
    if not text:
        return ""
    return ' '.join(text.strip().split())

# Helper function to parse senator info (e.g., "Nancy PelosiDemocratHouseCA" -> Democrat, House, CA)
def parse_senator_info(info: str) -> str:
    if not info:
        return "Unknown, Unknown, Unknown"
    
    party = "Unknown"
    branch = "Unknown"
    state = "Unknown"
    
    info = info.strip()
    
    if "Democrat" in info:
        party = "Democrat"
    elif "Republican" in info:
        party = "Republican"
    elif "Independent" in info:
        party = "Independent"
        
    if "Senate" in info:
        branch = "Senate"
    elif "House" in info:
        branch = "House"
        
    state_match = re.search(r'[A-Z]{2}$', info)
    if state_match:
        state = state_match.group()
    
    return f"{party}, {branch}, {state}"

# Helper function to parse date strings (e.g., "20 Jun2025", "12 Sept2024")
def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        logger.debug(f"Empty date string")
        return None
    
    # Normalize month abbreviations (e.g., "Sept" -> "Sep")
    month_mappings = {
        "Sept": "Sep",
  
    }
    normalized_date = date_str.strip()
    for wrong, right in month_mappings.items():
        normalized_date = normalized_date.replace(wrong, right)
    
    logger.debug(f"Normalized date: '{date_str}' -> '{normalized_date}'")
    
    formats = ["%d %b %Y","%d %b%Y", "%d %B %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(normalized_date, fmt)
        except (ValueError, TypeError):
            continue
    logger.debug(f"Failed to parse normalized date '{normalized_date}' with formats {formats}")
    return None

# Helper function to determine asset type
def is_valid_asset(ticker: str, include_stock: bool, include_option: bool) -> bool:
    return include_stock  # Assume all are stocks, as debug data shows only :US tickers

@app.get("/")
async def root():
    return {"message": "Capitol Trades API is running"}

async def fetch_page_content(base_url: str, params: dict) -> tuple[str, list]:
    """Fetch page content and extract rows with Playwright Async"""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        url = f"{base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        logger.info(f"Navigating to: {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle", timeout=60000)

        # Find trade rows
        trade_rows = await page.query_selector_all("tbody tr")
        logger.info(f"Found {len(trade_rows)} rows with selector 'tbody tr'")
        
        rows_data = []
        for i, row in enumerate(trade_rows):  # Skip header
            # Get cells
            cells = await row.query_selector_all("td")
            logger.debug(f"Row {i}: Found {len(cells)} cells")
            if len(cells) < 10:
                logger.debug(f"Row {i}: Skipped, only {len(cells)} cells found, expected 10")
                continue
            
            # Extract description by hovering over transaction type (cell 6)
            description = ""
            try:
                tx_cell = cells[6]  # Transaction type (e.g., "buy")
                await tx_cell.hover()
                await page.wait_for_timeout(500)  # Wait for tooltip
                tooltip = await page.query_selector(".q-tooltip, [role='tooltip'], [data-tooltip], .tooltip, .popover")
                if tooltip:
                    description = await tooltip.inner_text()
                    description = clean_text(description)
                    logger.debug(f"Row {i}: Description extracted: {description}")
                else:
                    logger.debug(f"Row {i}: No tooltip found for transaction cell")
            except Exception as e:
                logger.debug(f"Row {i}: Failed to extract description: {str(e)}")
            
            # Get cell texts
            cell_texts = []
            for cell in cells:
                text = await cell.inner_text()
                cell_texts.append(clean_text(text))
            
            rows_data.append({
                "cell_count": len(cells),
                "cell_contents": cell_texts,
                "description": description,
                "raw_html": await row.inner_html()
            })

        content = await page.content()
        await browser.close()
        logger.info(f"Page content length: {len(content)}")
        logger.debug(f"Page content snippet: {content[:200]}...")
        return content, rows_data

@app.get("/trades")
async def get_trades(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trade_type: str = "both",
    include_stock: bool = True,
    include_option: bool = True
):
    try:
        # Set default date range: last 30 days if not specified
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        # Parse date range for filtering
        try:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
            logger.debug(f"Date range: {start_date_dt} to {end_date_dt}")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

        # Validate trade_type
        if trade_type not in ["buy", "sell", "both"]:
            raise HTTPException(status_code=400, detail="Invalid trade_type. Use 'buy', 'sell', or 'both'.")

        # Construct URL with only politician filter
        base_url = "https://www.capitoltrades.com/trades"
        params = {"politician": POLITICIAN_MAPPING["Nancy Pelosi"]}
        
        # Fetch page content and rows
        content, rows_data = await fetch_page_content(base_url, params)
        
        # Parse HTML with BeautifulSoup for fallback
        soup = BeautifulSoup(content, "html.parser")
        trade_rows = soup.select("tbody tr")
        if not trade_rows:
            logger.warning("No trade rows found with 'tbody tr'. Falling back to all table rows...")
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                trade_rows = [row for row in rows if row.find_all("td")]
                if trade_rows:
                    logger.info(f"Fallback: found {len(trade_rows)} rows in table")
                    break
        
        if not trade_rows:
            logger.warning("No trade rows found in any table.")
            return {
                "trades": [],
                "debug_info": "No trade rows found. Check HTML structure in /debug endpoint with use_playwright=true."
            }

        trades = []
        for i, row_data in enumerate(rows_data, start=0):
            try:
                cell_count = row_data["cell_count"]
                cells = row_data["cell_contents"]
                description = row_data["description"]
                raw_html = row_data["raw_html"]
                
                logger.debug(f"Row {i}: Found {cell_count} cells: {cells[:50]}")
                if cell_count < 10:
                    logger.debug(f"Row {i}: Skipped, only {cell_count} cells found, expected 10. Raw HTML: {raw_html[:200]}")
                    continue
                
                # Map cells to fields
                senator_info_raw = cells[0]  # e.g., "Nancy PelosiDemocratHouseCA"
                senator = "Nancy Pelosi"
                senator_info = parse_senator_info(senator_info_raw)
                issuer_ticker = cells[1]  # e.g., "Broadcom IncAVGO:US"
                ticker_match = re.search(r'([A-Z]+:US)$', issuer_ticker)
                issuer = issuer_ticker.replace(ticker_match.group(0), '').strip() if ticker_match else issuer_ticker
                ticker = ticker_match.group(0) if ticker_match else ""
                publish_date = cells[2]  # e.g., "10 Jul2025"
                trade_date = cells[3]  # e.g., "20 Jun2025"
                days_filed_after = cells[4].replace("days", "").strip()  # e.g., "19"
                owner = cells[5]  # e.g., "Spouse"
                tx_type = cells[6]  # e.g., "buy"
                size = cells[7]  # e.g., "1M–5M"
                price = cells[8]  # e.g., "$80.00"
                
                # Log trade details before filtering
                logger.debug(f"Row {i}: publish_date={publish_date}, tx_type={tx_type}, ticker={ticker}, description={description}")

                # Filter by trade_date (include if parsing fails)
                publish_date_dt = parse_date(publish_date)
                if publish_date_dt and (publish_date_dt < start_date_dt or publish_date_dt > end_date_dt):
                    logger.debug(f"Row {i}: Skipped, publish_date {publish_date} (parsed: {publish_date_dt}) outside range {start_date} to {end_date}")
                    continue
                
                # Filter by trade type
                if trade_type != "both" and tx_type and trade_type.lower() not in tx_type.lower():
                    logger.debug(f"Row {i}: Skipped, tx_type {tx_type} does not match {trade_type}")
                    continue
                
                # Filter by asset type
                if not is_valid_asset(ticker, include_stock, include_option):
                    logger.debug(f"Row {i}: Skipped, ticker {ticker} does not match asset filter (stock={include_stock}, option={include_option})")
                    continue

                # Add trade
                trades.append({
                    "publish_date": publish_date,
                    "trade_date": trade_date,
                    "senator_name": senator,
                    "senator_info": senator_info,
                    "type": tx_type,
                    "size": size,
                    "issuer_trade": issuer,
                    "ticker": ticker,
                    "days_filed_after": days_filed_after,
                    "owner": owner,
                    "price": price,
                    "description": description
                })
                    
            except Exception as e:
                logger.warning(f"Error processing row {i}: {str(e)}. Raw HTML: {raw_html[:200]}")
                continue

        logger.info(f"Successfully parsed {len(trades)} trades")
        return {
            "trades": trades,
            "total_count": len(trades),
            "date_range": f"{start_date} to {end_date}",
            "filters": {
                "senator_name": "Nancy Pelosi (P000197)",
                "trade_type": trade_type,
                "include_stock": include_stock,
                "include_option": include_option
            }
        }
        
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing data: {str(e)}")

@app.get("/debug")
async def debug_page(
    use_playwright: bool = False,
    test_date_range: Optional[str] = None,
    test_trade_type: Optional[str] = None,
    test_asset_type: Optional[str] = None
):
    """Debug endpoint to examine the structure of Capitol Trades page"""
    try:
        base_url = "https://www.capitoltrades.com/trades"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        params = {"politician": POLITICIAN_MAPPING["Nancy Pelosi"]}
        if test_date_range:
            params["txDate"] = test_date_range
            logger.info(f"Testing date range: {test_date_range}")
        if test_trade_type:
            params["txType"] = test_trade_type
            logger.info(f"Testing trade type: {test_trade_type}")
        if test_asset_type:
            params["assetType"] = test_asset_type
            logger.info(f"Testing asset type: {test_asset_type}")
        
        if use_playwright:
            logger.info("Using Playwright Async for debug...")
            content, rows_data = await fetch_page_content(base_url, params)
        else:
            response = requests.get(base_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            content = response.text
            rows_data = []
            soup = BeautifulSoup(content, "html.parser")
            for row in soup.select("tbody tr"):
                cells = row.find_all("td")
                rows_data.append({
                    "cell_count": len(cells),
                    "cell_contents": [clean_text(cell.text)[:100] for cell in cells],
                    "description": "",
                    "raw_html": str(row)[:200]
                })
        
        soup = BeautifulSoup(content, "html.parser")
        
        # Find all tables
        tables = soup.find_all("table")
        table_info = []
        
        for i, table in enumerate(tables):
            rows = table.find_all("tr")
            sample_rows = []
            for j, row in enumerate(rows):
                cells = row.find_all("td")
                trade_date = clean_text(cells[3].text) if len(cells) > 3 else ""
                trade_date_dt = parse_date(trade_date) if trade_date else None
                description = rows_data[j]["description"] if j < len(rows_data) and use_playwright else ""
                sample_rows.append({
                    "row_index": j,
                    "classes": row.get('class', []),
                    "cell_count": len(cells),
                    "cell_contents": [clean_text(cell.text)[:100] for cell in cells],
                    "trade_date": trade_date,
                    "trade_date_parsed": trade_date_dt.isoformat() if trade_date_dt else "None",
                    "description": description,
                    "raw_html": str(row)[:200]
                })
            table_info.append({
                "table_index": i,
                "row_count": len(rows),
                "sample_rows": sample_rows
            })
        
        # Check for div-based structures
        other_containers = soup.find_all("div", class_=["trade-list", "trades", "trade-container", "q-tr"])
        container_info = []
        for i, container in enumerate(other_containers):
            items = container.find_all(["div", "li"], recursive=False)
            container_info.append({
                "container_index": i,
                "class": container.get('class', []),
                "item_count": len(items),
                "sample_content": clean_text(container.text)[:200]
            })
        
        # Test selectors
        selector_results = {}
        for selector in ["tr.q-tr", "tr.trade-row", "tr[class*='trade']", "tbody tr", ".q-tr", ".trade-item", "[data-trade]"]:
            elements = soup.select(selector)
            selector_results[selector] = {
                "count": len(elements),
                "sample": [clean_text(el.text)[:100] for el in elements[:2]]
            }
        
        return {
            "page_title": soup.title.text if soup.title else "No title",
            "tables_found": len(tables),
            "table_details": table_info,
            "other_containers": container_info,
            "raw_html_snippet": str(content)[:2000],
            "selector_results": selector_results,
            "source": "playwright_async" if use_playwright else "requests"
        }
        
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
#!/bin/bash

# Enhanced Capitol Trades API Debug Script
# This script will help you debug the soup content and find the right selectors

echo "🔍 Enhanced Capitol Trades Debug Script"
echo "======================================"

BASE_URL="http://localhost:8000"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if server is running
echo -e "${YELLOW}1. Checking server status...${NC}"
if ! curl -s "$BASE_URL" > /dev/null; then
    echo -e "${RED}❌ Server is not running!${NC}"
    echo "Start the server with: python capitol_trades_api.py"
    exit 1
fi
echo -e "${GREEN}✅ Server is running${NC}"

# Get detailed debug information
echo -e "\n${YELLOW}2. Getting detailed page analysis...${NC}"
curl -s "$BASE_URL/debug" | python3 -m json.tool > detailed_debug.json
echo "Detailed analysis saved to: detailed_debug.json"

# Save HTML content to files
echo -e "\n${YELLOW}3. Saving HTML content for manual inspection...${NC}"
curl -s "$BASE_URL/soup-content"
echo "HTML files saved: raw_html.html and prettified_html.html"

# Test basic trades endpoint with debug info
echo -e "\n${YELLOW}4. Testing trades endpoint (should show debug info)...${NC}"
curl -s "$BASE_URL/trades" | python3 -m json.tool > trades_debug.json
echo "Trades response with debug info saved to: trades_debug.json"

# Quick analysis of the debug files
echo -e "\n${YELLOW}5. Quick analysis of debug data...${NC}"

# Check if we have trade indicators
if command -v jq > /dev/null; then
    echo "Using jq for JSON analysis..."
    
    # Count trade indicators
    trade_class_count=$(jq '.trade_indicators.elements_with_trade_class | length' detailed_debug.json 2>/dev/null || echo "0")
    dollar_count=$(jq '.trade_indicators.elements_with_dollar_signs | length' detailed_debug.json 2>/dev/null || echo "0")
    politician_count=$(jq '.trade_indicators.politician_mentions | length' detailed_debug.json 2>/dev/null || echo "0")
    
    echo "Trade class elements found: $trade_class_count"
    echo "Dollar sign elements found: $dollar_count"  
    echo "Politician mentions found: $politician_count"
    
    # Show table analysis
    table_count=$(jq '.table_analysis | length' detailed_debug.json 2>/dev/null || echo "0")
    echo "Tables found: $table_count"
    
    if [ "$table_count" -gt 0 ]; then
        echo "Table details:"
        jq '.table_analysis[] | "Table \(.table_index): \(.row_count) rows, classes: \(.table_classes)"' detailed_debug.json 2>/dev/null || echo "Could not parse table details"
    fi
else
    echo "jq not installed, using basic grep analysis..."
    
    # Basic analysis without jq
    trade_elements=$(grep -o '"elements_with_trade_class":\[.*\]' detailed_debug.json | wc -l)
    dollar_elements=$(grep -o '\$[0-9,]*' detailed_debug.json | wc -l)
    
    echo "Approximate trade elements: $trade_elements"
    echo "Approximate dollar amounts: $dollar_elements"
fi

# Show files created
echo -e "\n${YELLOW}6. Files created for manual inspection:${NC}"
ls -la *.html *.json 2>/dev/null | grep -E '\.(html|json)$' || echo "No debug files found"

# Manual inspection suggestions
echo -e "\n${YELLOW}💡 Manual Debugging Steps:${NC}"
echo "1. Open 'prettified_html.html' in a browser to see the page structure"
echo "2. Look at 'detailed_debug.json' for trade indicators and table structure"
echo "3. Check 'trades_debug.json' for what the API is finding (or not finding)"
echo ""
echo "Search patterns to look for in the HTML:"
echo "- Elements with 'trade' in class names"
echo "- Table rows with politician names"  
echo "- Elements containing dollar amounts (\$)"
echo "- Buy/sell/purchase/sale text"

# Suggest next steps based on findings
echo -e "\n${YELLOW}📋 Next Debugging Steps:${NC}"
echo "1. Check if the page requires JavaScript (look for empty tables)"
echo "2. Look for the actual CSS selectors used by Capitol Trades"
echo "3. Check if there are anti-bot measures (CAPTCHA, rate limiting)"
echo "4. Verify the URL is correct and accessible"

# Quick test different endpoints
echo -e "\n${YELLOW}7. Testing different endpoints...${NC}"

echo "Testing /debug endpoint..."
curl -s "$BASE_URL/debug" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'Page title: {data.get(\"page_title\", \"Unknown\")}')
    print(f'Tables found: {data.get(\"tables_found\", 0)}')
except:
    print('Error parsing debug response')
"

echo -e "\n${GREEN}🎉 Debug analysis complete!${NC}"
echo "Check the generated files for detailed information about the page structure."
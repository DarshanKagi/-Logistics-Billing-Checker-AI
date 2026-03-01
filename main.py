"""
LOGISTICS BILLING CHECKER AI - FINAL PRODUCTION VERSION
Autonomous Invoice Reconciliation System for Supply Chain Teams
Project: Builder Challenge #8 - Supply Chain Team
ALL FIXES APPLIED:
✅ Footer Text Contrast - Dark background (#2c3e50) with white/green text
✅ Provider Detection - Filename + content detection (Delhivery detected correctly)
✅ Priority Field - ALL discrepancies have priority classification (High/Medium/Low)
✅ Non-Contracted Surcharge - ALL "Other Charges" flagged consistently
✅ Payout Columns - Includes Provider + Discrepancy_Amount columns
✅ Zone Mismatch Detection - Pincode-to-zone validation working
✅ Provider Template - Correct provider name in filename (delhivery_payout_*.csv)
✅ Consistent Naming - "Weight Overcharge" not "Base Rate"
✅ Info Savings Box - Now properly displays savings value
✅ Sample Files - Added sample invoice & contract download links for HF Spaces
✅ Gradio 6.0 Compatible - Fixed theme and style parameters
Demo Pitch: "847 line items. Manual: 4 hours. This tool: 3 minutes.
Found ₹18,400 in overcharges."
"""
import os
import json
import io
import tempfile
import pandas as pd
import pdfplumber
import gradio as gr
from groq import Groq
from typing import List, Dict, Any, Tuple, Optional
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import re

# ==============================================================================
# CONFIGURATION
# ==============================================================================
GROQ_API_KEY = "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"
GROQ_MODEL = "llama-3.1-8b-instant"

# Initialize Groq Client
client = Groq(api_key=GROQ_API_KEY)

# Supported Logistics Providers
SUPPORTED_PROVIDERS = {
    "delhivery": "Delhivery",
    "bluedart": "BlueDart",
    "ecom": "Ecom Express",
    "shadowfax": "Shadowfax",
    "shiprocket": "Shiprocket",
    "xpressbees": "XpressBees"
}

# Priority Discrepancy Types (from research blueprint)
PRIORITY_DISCREPANCIES = [
    "Weight Overcharge",
    "Zone Mismatch",
    "Non-Contracted Surcharge",
    "Duplicate Entry",
    "COD Fee",
    "RTO Charge",
    "Base Rate"
]

# Pincode to Zone Mapping (India - First 3 digits)
PINCODE_ZONE_MAP = {
    "110": "Zone-A",  # Delhi
    "111": "Zone-A",
    "112": "Zone-A",
    "400": "Zone-B",  # Mumbai
    "401": "Zone-B",
    "402": "Zone-B",
    "560": "Zone-C",  # Bangalore
    "561": "Zone-C",
    "562": "Zone-C",
    "700": "Zone-D",  # Kolkata
    "701": "Zone-D",
    "702": "Zone-D",
    "600": "Zone-B",  # Chennai
    "500": "Zone-C",  # Hyderabad
    "380": "Zone-B",  # Ahmedabad
    "411": "Zone-B",  # Pune
}

# ==============================================================================
# HELPER FUNCTIONS: PROVIDER DETECTION (FIX #1)
# ==============================================================================
def identify_provider(document_text: str, filename: str = "") -> str:
    """
    FIX #1: Enhanced provider detection with filename fallback.
    Checks filename FIRST (more reliable), then document content.
    """
    text_lower = document_text.lower()
    filename_lower = filename.lower()
    
    # Check filename first (more reliable)
    for key, provider in SUPPORTED_PROVIDERS.items():
        if key in filename_lower:
            print(f"✅ Provider detected from filename: {provider}")
            return provider
    
    # Check document content
    for key, provider in SUPPORTED_PROVIDERS.items():
        if key in text_lower:
            print(f"✅ Provider detected from content: {provider}")
            return provider
    
    print("⚠️ Provider not detected, using 'Unknown'")
    return "Unknown Provider"

# ==============================================================================
# HELPER FUNCTIONS: DOCUMENT EXTRACTION
# ==============================================================================
def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a PDF file using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"❌ Error extracting text from PDF: {e}")
    return text

def extract_tables_from_pdf(pdf_path: str) -> List[pd.DataFrame]:
    """Extracts tables from a PDF file using pdfplumber."""
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table and len(table) > 1:
                        df = pd.DataFrame(table[1:], columns=table[0])
                        tables.append(df)
    except Exception as e:
        print(f"❌ Error extracting tables from PDF: {e}")
    return tables

def extract_contract_data(contract_path: str) -> Dict[str, Any]:
    """
    Extracts rate cards and surcharge policies from Contract (Excel or PDF).
    Sheet 1: Rate Card, Sheet 2: Surcharges Policy
    """
    contract_rules = {
        "rate_card": None,
        "surcharges": None,
        "provider": "Unknown",
        "raw_text": ""
    }
    try:
        filename = os.path.basename(contract_path)
        file_name_lower = contract_path.lower()
        
        # Extract text for provider detection
        contract_rules["raw_text"] = extract_text_from_pdf(contract_path)
        contract_rules["provider"] = identify_provider(
            contract_rules["raw_text"], 
            filename
        )
        
        if file_name_lower.endswith('.xlsx') or file_name_lower.endswith('.xls'):
            xls = pd.ExcelFile(contract_path)
            
            # Sheet 1: Rate Card
            if len(xls.sheet_names) > 0:
                sheet_name = xls.sheet_names[0]
                df_rates = pd.read_excel(contract_path, sheet_name=sheet_name)
                # Clean column names
                df_rates.columns = [str(c).strip().lower().replace(' ', '_') for c in df_rates.columns]
                contract_rules["rate_card"] = df_rates
                
                print(f"✅ Rate Card Columns: {df_rates.columns.tolist()}")
                print(f"✅ Rate Card Rows: {len(df_rates)}")
            
            # Sheet 2: Surcharges
            if len(xls.sheet_names) > 1:
                sheet_name = xls.sheet_names[1]
                df_surcharges = pd.read_excel(contract_path, sheet_name=sheet_name)
                df_surcharges.columns = [str(c).strip().lower().replace(' ', '_') for c in df_surcharges.columns]
                contract_rules["surcharges"] = df_surcharges
                
                print(f"✅ Surcharge Columns: {df_surcharges.columns.tolist()}")
            
        elif file_name_lower.endswith('.pdf'):
            # Use LLM to extract contract data from PDF
            contract_rules = extract_contract_with_llm(contract_path, contract_rules)
            
    except Exception as e:
        print(f"❌ Error extracting contract: {e}")
    
    return contract_rules

def extract_contract_with_llm(contract_path: str, contract_rules: Dict) -> Dict:
    """Use LLM to extract structured data from contract PDF."""
    try:
        text = extract_text_from_pdf(contract_path)
        prompt = f"""
        Extract rate card and surcharge information from this logistics contract.
        Return ONLY valid JSON with this structure:
        {{
            "rate_card": [
                {{"zone": "Zone A", "weight_tier_kg": 1.0, "rate_per_kg": 50.0}}
            ],
            "surcharges": {{
                "cod_fee_flat": 50.0,
                "rto_charge_flat": 100.0,
                "fuel_surcharge_percent": 10.0
            }},
            "provider": "Provider Name"
        }}
        
        Contract Text:
        {text[:8000]}
        """
        
        response = call_groq_llm(prompt, json_response=True)
        
        if response:
            if "rate_card" in response and response["rate_card"]:
                contract_rules["rate_card"] = pd.DataFrame(response["rate_card"])
            if "surcharges" in response and response["surcharges"]:
                contract_rules["surcharges"] = pd.DataFrame([response["surcharges"]])
            if "provider" in response:
                contract_rules["provider"] = response["provider"]
            
    except Exception as e:
        print(f"⚠️ LLM contract extraction failed: {e}")
    
    return contract_rules

def extract_invoice_data(invoice_paths: List[str]) -> List[Dict[str, Any]]:
    """
    Extracts line items from multiple Invoice PDFs.
    Uses hybrid approach: pdfplumber + LLM for complex formats.
    """
    all_line_items = []
    for invoice_path in invoice_paths:
        try:
            filename = os.path.basename(invoice_path)
            raw_text = extract_text_from_pdf(invoice_path)
            provider = identify_provider(raw_text, filename)
            tables = extract_tables_from_pdf(invoice_path)
            
            # Try table extraction first
            if tables:
                main_table = find_main_line_item_table(tables)
                line_items = process_table_with_rules(main_table, provider, invoice_path)
                all_line_items.extend(line_items)
            else:
                # Fallback to LLM extraction for complex formats
                line_items = extract_invoice_with_llm(invoice_path, provider)
                all_line_items.extend(line_items)
            
        except Exception as e:
            print(f"❌ Error processing invoice {invoice_path}: {e}")
            continue
    
    print(f"✅ Total Line Items Extracted: {len(all_line_items)}")
    return all_line_items

def find_main_line_item_table(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """Find the main line-item table from extracted tables."""
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if 'awb' in cols or 'total' in cols or 'amount' in cols:
            return t
    return tables[0] if tables else pd.DataFrame()

def process_table_with_rules(table: pd.DataFrame, provider: str, source_file: str) -> List[Dict]:
    """Process table with column mapping rules."""
    line_items = []
    if table.empty:
        return line_items
    
    # Normalize column names
    table.columns = [str(c).strip().lower().replace(' ', '_') for c in table.columns]
    
    # Column mapping for universal extraction
    col_mapping = {
        'awb': ['awb', 'awb_no', 'air_waybill', 'consignment', 'tracking'],
        'origin_pin': ['orig', 'origin', 'from_pin', 'source_pin', 'from_pincode'],
        'dest_pin': ['dest', 'destination', 'to_pin', 'dest_pin', 'to_pincode'],
        'weight_kg': ['wt', 'weight', 'weight_kg', 'kg', 'gross_weight'],
        'zone': ['zn', 'zone'],
        'base_charge': ['base', 'base_charge', 'freight', 'shipping_charge'],
        'cod_charge': ['cod', 'cod_charge', 'cod_fee', 'collection_fee'],
        'rto_charge': ['rto', 'rto_charge', 'return_charge', 'return_to_origin'],
        'other_charge': ['oth', 'other', 'surcharge', 'fuel_surcharge', 'additional'],
        'total_charge': ['total', 'total_charge', 'amount', 'payable']
    }
    
    for idx, row in table.iterrows():
        try:
            clean_row = {}
            
            for standard_key, variations in col_mapping.items():
                for var in variations:
                    if var in table.columns:
                        val = row.get(var, '')
                        clean_row[standard_key] = str(val).strip() if pd.notna(val) else ''
                        break
                if standard_key not in clean_row:
                    clean_row[standard_key] = ''
            
            # Convert numeric fields
            for numeric_field in ['weight_kg', 'base_charge', 'cod_charge', 'rto_charge', 'other_charge', 'total_charge']:
                try:
                    val = clean_row.get(numeric_field, '0')
                    clean_row[numeric_field] = float(str(val).replace(',', '')) if val else 0.0
                except:
                    clean_row[numeric_field] = 0.0
            
            clean_row['provider'] = provider
            clean_row['source_file'] = os.path.basename(source_file)
            
            # Skip header rows or empty AWB
            if clean_row.get('awb', '') and 'awb' not in str(clean_row['awb']).lower():
                line_items.append(clean_row)
            
        except Exception as e:
            print(f"⚠️ Error processing row {idx}: {e}")
            continue
    
    return line_items

def extract_invoice_with_llm(invoice_path: str, provider: str) -> List[Dict]:
    """Use LLM to extract line items from complex invoice formats."""
    try:
        text = extract_text_from_pdf(invoice_path)
        prompt = f"""
        Extract all line items from this logistics invoice. Return ONLY valid JSON array.
        Each item should have: awb, weight_kg, zone, base_charge, cod_charge, rto_charge, 
        other_charge, total_charge, origin_pin, dest_pin
        
        Invoice Text:
        {text[:8000]}
        """
        
        response = call_groq_llm(prompt, json_response=True)
        
        line_items = []
        if response and isinstance(response, list):
            for item in response:
                item['provider'] = provider
                item['source_file'] = os.path.basename(invoice_path)
                line_items.append(item)
        
        return line_items
        
    except Exception as e:
        print(f"⚠️ LLM invoice extraction failed: {e}")
        return []

def call_groq_llm(prompt: str, json_response: bool = False) -> Any:
    """Wrapper for Groq API calls with error handling."""
    try:
        messages = [{"role": "user", "content": prompt}]
        response_format = {"type": "json_object"} if json_response else None
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.1,
            response_format=response_format,
            max_tokens=2000
        )
        
        content = completion.choices[0].message.content
        if json_response:
            return json.loads(content)
        return content
    except Exception as e:
        print(f"❌ Groq API Error: {e}")
        return None

# ==============================================================================
# VALIDATION ENGINE - FULLY CORRECTED
# ==============================================================================
def get_priority(charge_component: str, discrepancy_amount: float) -> str:
    """
    FIX #2: Assign priority based on discrepancy type and amount.
    Ensures ALL discrepancies have priority classification.
    """
    high_priority_types = [
        "Weight Overcharge",
        "Zone Mismatch",
        "Non-Contracted Surcharge",
        "Duplicate Entry"
    ]
    if charge_component in high_priority_types:
        return "High"
    elif discrepancy_amount > 50:
        return "High"
    elif charge_component in ["COD Fee", "RTO Charge"]:
        return "Medium"
    else:
        return "Low"

def validate_zone(dest_pin: str, charged_zone: str) -> Tuple[bool, str]:
    """
    FIX #5: Validate destination pincode matches charged zone.
    Returns (is_valid, reason_if_invalid)
    """
    if not dest_pin or len(dest_pin) < 3:
        return True, ""  # Can't validate without pincode
    
    pin_prefix = dest_pin[:3]
    expected_zone = PINCODE_ZONE_MAP.get(pin_prefix, None)
    
    if expected_zone:
        # Normalize zone names for comparison
        charged_zone_normalized = charged_zone.strip().lower().replace('-', '').replace(' ', '')
        expected_zone_normalized = expected_zone.strip().lower().replace('-', '').replace(' ', '')
        
        if charged_zone_normalized != expected_zone_normalized:
            return False, f"Pincode {dest_pin} should be {expected_zone}, charged {charged_zone}"
    
    return True, ""

def validate_charges(line_items: List[Dict], contract_rules: Dict) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Core Validation Logic - FULLY CORRECTED VERSION
    Returns: (discrepancies, payout_data, stats)
    """
    discrepancies = []
    payout_records = {}
    seen_awbs = set()
    
    rate_card = contract_rules.get("rate_card")
    surcharges = contract_rules.get("surcharges")
    provider = contract_rules.get("provider", "Unknown")
    
    # ========== BUILD RATE LOOKUP ==========
    rate_lookup = {}
    if rate_card is not None and not rate_card.empty:
        for _, row in rate_card.iterrows():
            try:
                zone = str(row.get('zone', 'all')).strip().lower()
                tier = float(row.get('weight_tier_kg', 0))
                fixed_rate = float(row.get('rate_per_kg', 0))
                
                if zone not in rate_lookup:
                    rate_lookup[zone] = []
                rate_lookup[zone].append({'tier': tier, 'fixed_rate': fixed_rate})
            except Exception as e:
                print(f"⚠️ Error processing rate card row: {e}")
                continue
        
        # Sort tiers for each zone (ascending)
        for zone in rate_lookup:
            rate_lookup[zone].sort(key=lambda x: x['tier'])
    
    print(f"✅ Rate Lookup Zones: {list(rate_lookup.keys())}")
    
    # ========== EXTRACT SURCHARGE VALUES ==========
    cod_fee_flat = 50.0  # Default fallback
    rto_fee_flat = 100.0  # Default fallback
    
    if surcharges is not None and not surcharges.empty:
        cod_columns = ['cod_fee_flat', 'cod_flat', 'cod_fee', 'cod']
        rto_columns = ['rto_charge_flat', 'rto_flat', 'rto_charge', 'rto']
        
        for col in cod_columns:
            if col in surcharges.columns:
                try:
                    val = surcharges.iloc[0].get(col)
                    if val is not None and pd.notna(val):
                        cod_fee_flat = float(val)
                        break
                except:
                    pass
        
        for col in rto_columns:
            if col in surcharges.columns:
                try:
                    val = surcharges.iloc[0].get(col)
                    if val is not None and pd.notna(val):
                        rto_fee_flat = float(val)
                        break
                except:
                    pass
    
    print(f"✅ Using COD Fee: ₹{cod_fee_flat}, RTO Fee: ₹{rto_fee_flat}")
    
    # ========== TRACK TOTALS ==========
    total_billed_all = 0.0
    error_by_type = {priority: 0 for priority in PRIORITY_DISCREPANCIES}
    
    # ========== VALIDATE EACH LINE ITEM ==========
    for item in line_items:
        awb = item.get('awb', 'UNKNOWN')
        item_provider = item.get('provider', provider)
        
        billed_base = float(item.get('base_charge', 0.0) or 0.0)
        billed_cod = float(item.get('cod_charge', 0.0) or 0.0)
        billed_rto = float(item.get('rto_charge', 0.0) or 0.0)
        billed_oth = float(item.get('other_charge', 0.0) or 0.0)
        billed_total = float(item.get('total_charge', 0.0) or 0.0)
        
        weight = float(item.get('weight_kg', 0.0) or 0.0)
        zone = str(item.get('zone', '')).strip().lower()
        dest_pin = str(item.get('dest_pin', ''))
        
        # Add to total billed (ALL items, including duplicates)
        total_billed_all += billed_base + billed_cod + billed_rto + billed_oth
        
        verified_total = 0.0
        
        # ----- 1. DUPLICATE AWB CHECK -----
        if awb in seen_awbs:
            priority = get_priority("Duplicate Entry", billed_total)
            discrepancies.append({
                "AWB": awb,
                "charge_component": "Duplicate Entry",
                "billed_value": round(billed_total, 2),
                "contracted_value": 0.0,
                "discrepancy_amount": round(billed_total, 2),
                "reason": "AWB already processed in this batch - possible double billing",
                "priority": priority
            })
            error_by_type["Duplicate Entry"] = error_by_type.get("Duplicate Entry", 0) + 1
            continue
        seen_awbs.add(awb)
        
        # ----- 2. ZONE MISMATCH CHECK -----
        zone_valid, zone_reason = validate_zone(dest_pin, zone)
        if not zone_valid:
            priority = get_priority("Zone Mismatch", billed_base)
            discrepancies.append({
                "AWB": awb,
                "charge_component": "Zone Mismatch",
                "billed_value": round(billed_base, 2),
                "contracted_value": 0.0,
                "discrepancy_amount": round(billed_base, 2),
                "reason": zone_reason,
                "priority": priority
            })
            error_by_type["Zone Mismatch"] = error_by_type.get("Zone Mismatch", 0) + 1
        
        # ----- 3. BASE RATE VALIDATION (Weight & Zone) -----
        expected_base = billed_base
        zone_matched = False
        tiers = None
        
        if zone in rate_lookup:
            zone_matched = True
            tiers = rate_lookup[zone]
        elif 'all' in rate_lookup:
            zone_matched = True
            tiers = rate_lookup['all']
        else:
            for lookup_zone in rate_lookup:
                if zone in lookup_zone or lookup_zone in zone:
                    zone_matched = True
                    tiers = rate_lookup[lookup_zone]
                    break
        
        if zone_matched and tiers:
            applicable = None
            for tier_info in tiers:
                if weight <= tier_info['tier']:
                    applicable = tier_info
                    break
            
            if applicable is None and tiers:
                applicable = tiers[-1]
            
            if applicable:
                expected_base = applicable['fixed_rate']
        
        # Check for rate deviation
        if expected_base > 0 and billed_base > expected_base and (billed_base - expected_base) > 1.0:
            discrepancy_type = "Weight Overcharge"
            priority = get_priority(discrepancy_type, billed_base - expected_base)
            discrepancies.append({
                "AWB": awb,
                "charge_component": discrepancy_type,
                "billed_value": round(billed_base, 2),
                "contracted_value": round(expected_base, 2),
                "discrepancy_amount": round(billed_base - expected_base, 2),
                "reason": f"Rate deviation. Expected ₹{expected_base:.2f} for {weight}kg in {zone.upper()}",
                "priority": priority
            })
            error_by_type[discrepancy_type] = error_by_type.get(discrepancy_type, 0) + 1
            verified_total += expected_base
        else:
            verified_total += billed_base
        
        # ----- 4. COD FEE CHECK -----
        if billed_cod > 0:
            if billed_cod > cod_fee_flat and (billed_cod - cod_fee_flat) > 1.0:
                priority = get_priority("COD Fee", billed_cod - cod_fee_flat)
                discrepancies.append({
                    "AWB": awb,
                    "charge_component": "COD Fee",
                    "billed_value": round(billed_cod, 2),
                    "contracted_value": round(cod_fee_flat, 2),
                    "discrepancy_amount": round(billed_cod - cod_fee_flat, 2),
                    "reason": f"COD fee overcharge. Contracted flat fee is ₹{cod_fee_flat}",
                    "priority": priority
                })
                error_by_type["COD Fee"] = error_by_type.get("COD Fee", 0) + 1
                verified_total += cod_fee_flat
            else:
                verified_total += billed_cod
        
        # ----- 5. RTO FEE CHECK -----
        if billed_rto > 0:
            if billed_rto > rto_fee_flat and (billed_rto - rto_fee_flat) > 1.0:
                priority = get_priority("RTO Charge", billed_rto - rto_fee_flat)
                discrepancies.append({
                    "AWB": awb,
                    "charge_component": "RTO Charge",
                    "billed_value": round(billed_rto, 2),
                    "contracted_value": round(rto_fee_flat, 2),
                    "discrepancy_amount": round(billed_rto - rto_fee_flat, 2),
                    "reason": f"RTO overcharge. Contracted flat fee is ₹{rto_fee_flat}",
                    "priority": priority
                })
                error_by_type["RTO Charge"] = error_by_type.get("RTO Charge", 0) + 1
                verified_total += rto_fee_flat
            else:
                verified_total += billed_rto
        
        # ----- 6. OTHER SURCHARGES CHECK (ALL flagged) -----
        if billed_oth > 0:
            priority = get_priority("Non-Contracted Surcharge", billed_oth)
            discrepancies.append({
                "AWB": awb,
                "charge_component": "Non-Contracted Surcharge",
                "billed_value": round(billed_oth, 2),
                "contracted_value": 0.0,
                "discrepancy_amount": round(billed_oth, 2),
                "reason": "Non-contracted surcharge detected - requires verification",
                "priority": priority
            })
            error_by_type["Non-Contracted Surcharge"] = error_by_type.get("Non-Contracted Surcharge", 0) + 1
            # Do NOT add to verified total (unauthorized charge)
        
        # ----- RECORD PAYOUT DATA -----
        if awb not in payout_records:
            payout_records[awb] = {
                "verified_total": 0.0,
                "billed_total": 0.0,
                "provider": item_provider,
                "awb": awb
            }
        payout_records[awb]["verified_total"] += verified_total
        payout_records[awb]["billed_total"] += (billed_base + billed_cod + billed_rto + billed_oth)

    # ========== PREPARE PAYOUT LIST ==========
    payout_list = []
    for awb, data in payout_records.items():
        payout_list.append({
            "AWB": awb,
            "Provider": data["provider"],
            "Billed_Total": round(data["billed_total"], 2),
            "Verified_Total": round(data["verified_total"], 2),
            "Approved_for_Payment": round(data["verified_total"], 2),
            "Status": "Verified" if data["billed_total"] == data["verified_total"] else "Adjusted",
            "Discrepancy_Amount": round(data["billed_total"] - data["verified_total"], 2)
        })

    # ========== CALCULATE STATS ==========
    total_verified = sum(r["verified_total"] for r in payout_records.values())
    savings = total_billed_all - total_verified
    
    duplicate_charges = sum(
        disc["discrepancy_amount"] 
        for disc in discrepancies 
        if disc["charge_component"] == "Duplicate Entry"
    )
    
    # Priority breakdown
    high_priority_savings = sum(
        disc["discrepancy_amount"]
        for disc in discrepancies
        if disc.get("priority") == "High"
    )
    
    stats = {
        "total_billed": total_billed_all,
        "total_verified": total_verified,
        "savings": savings,
        "savings_percent": (savings / total_billed_all * 100) if total_billed_all > 0 else 0,
        "duplicate_savings": duplicate_charges,
        "high_priority_savings": high_priority_savings,
        "error_count": len(discrepancies),
        "error_by_type": error_by_type,
        "total_awbs": len(payout_records),
        "total_line_items": len(line_items),
        "processing_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider
    }
    
    print(f"✅ Validation Complete: {len(discrepancies)} discrepancies, Savings: ₹{stats['savings']}")
    print(f"📊 Total Billed: ₹{total_billed_all}, Verified: ₹{total_verified}")
    
    return discrepancies, payout_list, stats

# ==============================================================================
# FILE GENERATION HELPERS
# ==============================================================================
def create_temp_csv(data: List[Dict], prefix: str) -> str:
    """Create a temporary CSV file and return its path."""
    if not data:
        return None
    df = pd.DataFrame(data)
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', prefix=prefix)
    df.to_csv(temp_file.name, index=False)
    return temp_file.name

def create_provider_template(payout_list: List[Dict], provider: str) -> str:
    """
    FIX #7: Create provider-specific template format with correct provider name.
    """
    template_data = []
    for item in payout_list:
        template_data.append({
            "AWB_Number": item.get("AWB", ""),
            "Payment_Amount": item.get("Approved_for_Payment", 0),
            "Status": item.get("Status", "Verified"),
            "Processing_Date": datetime.now().strftime("%Y-%m-%d"),
            "Provider": provider
        })
    
    # Use provider name in filename
    provider_safe = provider.lower().replace(' ', '_').replace('-', '_')
    if provider_safe == "unknown":
        provider_safe = "unknown_provider"
    
    return create_temp_csv(template_data, f"{provider_safe}_payout_")

# ==============================================================================
# DASHBOARD & VISUALIZATION
# ==============================================================================
def create_dashboard_metrics(stats: Dict) -> str:
    """Create HTML dashboard with key metrics."""
    savings = stats.get('savings', 0)
    duplicate_charges = stats.get('duplicate_savings', 0)
    high_priority = stats.get('high_priority_savings', 0)
    
    # FIX #1: Dark background for footer with high contrast text
    metric_html = f"""
    <div style="font-family: 'Segoe UI', sans-serif; padding: 20px; background: #f8f9fa; border-radius: 12px;">
        <h2 style="text-align: center; margin-bottom: 30px; color: #2c3e50;">📊 Billing Audit Summary</h2>
        
        <div style="display: flex; gap: 20px; flex-wrap: wrap; justify-content: center;">
            <div style="flex: 1; min-width: 200px; padding: 25px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin: 0; opacity: 0.9;">Total Billed</h3>
                <h1 style="margin: 10px 0 0 0; font-size: 2.5em;">₹{stats['total_billed']:,.2f}</h1>
                <small>{stats['total_line_items']} line items</small>
            </div>
            
            <div style="flex: 1; min-width: 200px; padding: 25px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); border-radius: 12px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin: 0; opacity: 0.9;">Verified Amount</h3>
                <h1 style="margin: 10px 0 0 0; font-size: 2.5em;">₹{stats['total_verified']:,.2f}</h1>
                <small>{stats['total_awbs']} unique AWBs</small>
            </div>
            
            <div style="flex: 1; min-width: 200px; padding: 25px; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); border-radius: 12px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="margin: 0; opacity: 0.9;">💰 Total Savings</h3>
                <h1 style="margin: 10px 0 0 0; font-size: 2.5em; color: white;">₹{savings:,.2f}</h1>
                <small>{stats['savings_percent']:.1f}% of billed amount</small>
            </div>
        </div>
        
        <div style="display: flex; gap: 20px; margin-top: 20px; justify-content: center; flex-wrap: wrap;">
            <div style="padding: 15px 30px; background: white; border-radius: 8px; text-align: center; border: 1px solid #ddd;">
                <strong style="color: #e74c3c;">🔴 High Priority Savings</strong><br>
                <span style="font-size: 1.5em; color: #e74c3c;">₹{high_priority:,.2f}</span>
            </div>
            
            <div style="padding: 15px 30px; background: white; border-radius: 8px; text-align: center; border: 1px solid #ddd;">
                <strong style="color: #f39c12;">🟠 Duplicate Charges</strong><br>
                <span style="font-size: 1.5em; color: #f39c12;">₹{duplicate_charges:,.2f}</span>
            </div>
            
            <div style="padding: 15px 30px; background: white; border-radius: 8px; text-align: center; border: 1px solid #ddd;">
                <strong style="color: #27ae60;">🟢 Errors Found</strong><br>
                <span style="font-size: 1.5em; color: #27ae60;">{stats.get('error_count', 0)}</span>
            </div>
        </div>
        
        <!-- FIX #1: Dark background (#2c3e50) with high contrast text -->
        <div style="margin-top: 20px; padding: 15px; background: #2c3e50; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
            <strong style="color: #ffffff;">⏱️ Processing Time:</strong> <span style="color: #ecf0f1;">{stats.get('processing_time', 'N/A')}</span> | 
            <strong style="color: #ffffff;">📈 ROI:</strong> <span style="color: #2ecc71; font-weight: bold;">Every minute saved = ₹{(savings/5) if savings > 0 else 0:.2f} recovered</span>
        </div>
    </div>
    """
    
    return metric_html

def create_charts(discrepancies: List[Dict]) -> Tuple[Any, Any]:
    """Create visualization charts for discrepancies."""
    fig_type = None
    fig_provider = None
    
    if discrepancies:
        disc_df = pd.DataFrame(discrepancies)
        
        # Chart 1: Overcharges by Type (Priority-based)
        type_summary = disc_df.groupby('charge_component')['discrepancy_amount'].sum().reset_index()
        type_summary = type_summary.sort_values('discrepancy_amount', ascending=False)
        
        fig_type = px.bar(
            type_summary,
            x='charge_component',
            y='discrepancy_amount',
            title='💸 Overcharges by Type (Priority Ranked)',
            color='discrepancy_amount',
            color_continuous_scale='Reds',
            labels={'charge_component': 'Error Type', 'discrepancy_amount': 'Amount (₹)'}
        )
        fig_type.update_layout(height=400, showlegend=False)
        
        # Chart 2: Discrepancy Distribution by Priority
        priority_summary = disc_df.groupby('priority').size().reset_index(name='count')
        if len(priority_summary) > 0:
            fig_provider = px.pie(
                priority_summary,
                values='count',
                names='priority',
                title='📋 Discrepancy Distribution by Priority',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_provider.update_layout(height=400)
    
    if fig_type is None:
        fig_type = go.Figure()
        fig_type.add_annotation(text="✅ No Discrepancies Found!", 
                               xref="paper", yref="paper",
                               x=0.5, y=0.5, showarrow=False,
                               font=dict(size=20, color="green"))
        fig_type.update_layout(height=400)
    
    if fig_provider is None:
        fig_provider = go.Figure()
        fig_provider.add_annotation(text="✅ All Charges Verified!", 
                                   xref="paper", yref="paper",
                                   x=0.5, y=0.5, showarrow=False,
                                   font=dict(size=20, color="green"))
        fig_provider.update_layout(height=400)
    
    return fig_type, fig_provider

# ==============================================================================
# MAIN PROCESSING FUNCTION
# ==============================================================================
def process_billing(invoices, contract):
    """Main processing function for Gradio interface."""
    if not invoices or not contract:
        return (
            "❌ Please upload both invoices and a contract.",
            None, None, None, None,
            "No data to display",
            None, None, None,
            0
        )
    
    # Handle single file vs list
    invoice_paths = []
    if isinstance(invoices, list):
        invoice_paths = [f.name for f in invoices]
    else:
        invoice_paths = [invoices.name]
    
    contract_path = contract.name
    
    try:
        print("\n" + "="*60)
        print("🚀 STARTING BILLING VALIDATION")
        print("="*60)
        
        # Stage 1: Extract
        print("📥 Stage 1: Extracting data from documents...")
        contract_rules = extract_contract_data(contract_path)
        line_items = extract_invoice_data(invoice_paths)
        
        if not line_items:
            return (
                "❌ No line items extracted from invoices. Please check PDF format.",
                None, None, None, None,
                "Extraction failed",
                None, None, None,
                0
            )
        
        # Stage 2: Validate
        print("🔍 Stage 2: Validating charges against contract...")
        discrepancies, payout_data, stats = validate_charges(line_items, contract_rules)
        
        # Stage 3: Generate Reports
        print("📄 Stage 3: Generating reports...")
        disc_csv_path = create_temp_csv(discrepancies if discrepancies else [], "discrepancy_")
        payout_csv_path = create_temp_csv(payout_data if payout_data else [], "payout_")
        provider_template_path = create_provider_template(payout_data, contract_rules.get('provider', 'Unknown'))
        
        # Create Dashboard
        metric_html = create_dashboard_metrics(stats)
        fig_type, fig_provider = create_charts(discrepancies)
        
        status_msg = f"✅ Processing Complete! Found {stats['error_count']} discrepancies. Savings: ₹{stats['savings']:,.2f}"
        
        print("="*60)
        print("🎉 VALIDATION COMPLETE")
        print("="*60)
        
        return (
            status_msg,
            disc_csv_path,
            payout_csv_path,
            fig_type,
            fig_provider,
            metric_html,
            len(line_items),
            contract_rules.get('provider', 'Unknown'),
            provider_template_path,
            stats.get('savings', 0)
        )
        
    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"❌ {error_msg}")
        return (
            error_msg,
            None, None, None, None,
            f"<div style='color: red; padding: 20px;'>{error_msg}</div>",
            0,
            "Error",
            None,
            0
        )

# ==============================================================================
# GRADIO UI DEFINITION (GRADIO 6.0 COMPATIBLE)
# ==============================================================================
with gr.Blocks(title="Logistics Billing Checker AI") as demo:
    gr.Markdown("""
    # 🚚 Logistics Billing Checker AI
    ### Autonomous Invoice Reconciliation for Supply Chain Teams
    **Demo Pitch:** "847 line items. Manual: 4 hours. This tool: 3 minutes. Found ₹18,400 in overcharges."
    """)
    
    with gr.Accordion("📋 Project Details & Challenge Statement", open=False):
        gr.Markdown("""
        **Problem:** D2C brands ship lakhs of orders per year through logistics partners. 
        Manual invoice checking takes 3-5 days per billing cycle.
        
        **Solution:** AI reads invoices + contracts, extracts data, cross-checks rates, 
        flags discrepancies, and prepares clean payout files.
        
        **Success Criteria:**
        - ✅ >95% field extraction accuracy across different invoice formats
        - ✅ Catches rate discrepancies, duplicate charges, and non-contracted surcharges
        - ✅ Produces payout-ready output for finance team
        - ✅ Processes full invoice batch in minutes, not days
        - ✅ Works across multiple logistics providers without manual configuration
        
        **Supported Providers:** Delhivery, BlueDart, Ecom Express, Shadowfax, Shiprocket, XpressBees
        """)
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 Upload Documents")
            
            # Invoice Upload Section
            gr.Markdown("**1. Upload Invoices (PDF)**")
            invoice_input = gr.File(
                label="Upload Invoices (PDF)",
                file_count="multiple",
                file_types=[".pdf"],
                height=150
            )
            # Sample Invoice Download Link
            gr.HTML("""
            <div style="margin-top: 10px; padding: 10px; background: #e8f4f8; border-radius: 8px; border-left: 4px solid #3498db;">
                <p style="margin: 0 0 8px 0; font-weight: bold; color: #2c3e50;">📎 Need a sample invoice to test?</p>
                <a href="https://drive.google.com/uc?export=download&id=1jkryF6Hf2DPWNnegYJOBfTbF2n7UBQJO" 
                   target="_blank" 
                   style="display: inline-block; padding: 8px 16px; background: #3498db; color: white; 
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                   ⬇️ Download Sample Invoice (PDF)
                </a>
                <p style="margin: 8px 0 0 0; font-size: 12px; color: #7f8c8d;">
                    Click to download, then upload above for testing
                </p>
            </div>
            """)
            
            gr.Markdown("<div style='margin-top: 20px;'><b>2. Upload Contract (Excel/PDF)</b></div>")
            contract_input = gr.File(
                label="Upload Contract (Excel/PDF)",
                file_count="single",
                file_types=[".pdf", ".xlsx", ".xls"],
                height=100
            )
            # Sample Contract Download Link
            gr.HTML("""
            <div style="margin-top: 10px; padding: 10px; background: #e8f8e8; border-radius: 8px; border-left: 4px solid #27ae60;">
                <p style="margin: 0 0 8px 0; font-weight: bold; color: #2c3e50;">📎 Need a sample contract to test?</p>
                <a href="https://docs.google.com/spreadsheets/d/1iHYqpe7qmIg5lnj4Szp5L3n1xZSOw2tr/export?format=xlsx" 
                   target="_blank" 
                   style="display: inline-block; padding: 8px 16px; background: #27ae60; color: white; 
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                   ⬇️ Download Sample Contract (Excel)
                </a>
                <p style="margin: 8px 0 0 0; font-size: 12px; color: #7f8c8d;">
                    Click to download, then upload above for testing
                </p>
            </div>
            """)
            
            process_btn = gr.Button(
                "🔍 Validate & Generate Report", 
                variant="primary", 
                size="lg"
            )
        
        with gr.Column(scale=1):
            gr.Markdown("### 📥 Download Reports")
            status_output = gr.Textbox(label="Status", interactive=False)
            disc_download = gr.File(label="📊 Discrepancy Report (CSV)", interactive=False)
            payout_download = gr.File(label="💰 Payout File (CSV)", interactive=False)
            provider_template_download = gr.File(label="📦 Provider Template (CSV)", interactive=False)
    
    metric_output = gr.HTML()
    
    gr.Markdown("### 📈 Analytics Dashboard")
    with gr.Row():
        chart_type = gr.Plot(label="Overcharges by Type")
        chart_provider = gr.Plot(label="Error Distribution by Priority")
    
    with gr.Row():
        info_lines = gr.Number(label="Total Line Items Processed", interactive=False)
        info_provider = gr.Textbox(label="Contract Provider", interactive=False)
        info_savings = gr.Number(label="Total Savings (₹)", interactive=False)
    
    process_btn.click(
        fn=process_billing,
        inputs=[invoice_input, contract_input],
        outputs=[
            status_output,
            disc_download,
            payout_download,
            chart_type,
            chart_provider,
            metric_output,
            info_lines,
            info_provider,
            provider_template_download,
            info_savings
        ]
    )
    
    gr.Markdown("---")
    gr.Markdown("""
    ### ℹ️ How It Works
    
    **Stage 1 — Extract:** AI reads invoices and pulls AWB, weight, zone, and all charges
    
    **Stage 2 — Check:** Cross-verifies against contracted rates (weight, zone, COD, RTO, surcharges)
    
    **Stage 3 — Prepare:** Generates discrepancy report + verified payout file + provider template
    
    **Priority Detection:** Weight Overcharge → Zone Mismatch → Non-Contracted Surcharges → Base Rate → COD/RTO → Duplicates
    
    **Architecture:** Hybrid AI (Unified Document Understanding + Rules Engine)
    """)
    
    gr.Markdown("""
    ### 📊 Key Performance Indicators (KPIs)
    
    | Metric | Target | Business Impact |
    |--------|--------|-----------------|
    | Extraction Accuracy | >95% | Reliable data foundation |
    | Processing Time | <30 minutes | 95% time reduction |
    | Error Detection | All priority types | Maximum cost recovery |
    | ROI | Measurable savings | Direct financial impact |
    """)

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Starting Logistics Billing Checker AI...")
    print("📌 Using Groq Model:", GROQ_MODEL)
    print("📌 Supported Providers:", list(SUPPORTED_PROVIDERS.values()))
    print("📌 Priority Discrepancies:", PRIORITY_DISCREPANCIES[:3])
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft()  # FIX: Moved theme to launch() for Gradio 6.0
    )
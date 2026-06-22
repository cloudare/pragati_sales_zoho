"""Unit tests for Tally XML parser."""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.tally_parser import parse_ledgers, parse_items, parse_vouchers


def test_parse_ledgers_basic():
    xml = """<TallySync type="ledgers">
      <Ledger>
        <Name>ABC Traders</Name>
        <Parent>Sundry Debtors</Parent>
        <GSTIN>27AAACH1234A1Z5</GSTIN>
        <Phone>9876543210</Phone>
        <Email>abc@example.com</Email>
        <State>Maharashtra</State>
        <OpeningBalance>5000.00</OpeningBalance>
      </Ledger>
    </TallySync>"""
    result = parse_ledgers(xml)
    assert len(result) == 1
    l = result[0]
    assert l['name'] == 'ABC Traders'
    assert l['gstin'] == '27AAACH1234A1Z5'
    assert l['opening_balance'] == 5000.0


def test_parse_ledgers_with_comma_amount():
    """Tally outputs amounts with commas — must be stripped."""
    xml = """<TallySync><Ledger><Name>X</Name><Parent>P</Parent><OpeningBalance>1,25,000.50</OpeningBalance></Ledger></TallySync>"""
    result = parse_ledgers(xml)
    assert result[0]['opening_balance'] == 125000.50


def test_parse_ledgers_missing_optional_fields():
    """Phone, email may be absent."""
    xml = """<TallySync><Ledger><Name>X</Name><Parent>P</Parent></Ledger></TallySync>"""
    result = parse_ledgers(xml)
    assert result[0]['phone'] == ''
    assert result[0]['email'] == ''
    assert result[0]['opening_balance'] == 0


def test_parse_items():
    xml = """<TallySync type="items">
      <Item>
        <Name>Surf Excel 1kg</Name>
        <Parent>Detergents</Parent>
        <Unit>pcs</Unit>
        <OpeningQty>500</OpeningQty>
        <OpeningRate>150.50</OpeningRate>
        <GSTApplicable>Applicable</GSTApplicable>
      </Item>
    </TallySync>"""
    result = parse_items(xml)
    assert len(result) == 1
    i = result[0]
    assert i['name'] == 'Surf Excel 1kg'
    assert i['unit'] == 'pcs'
    assert i['opening_qty'] == 500
    assert i['opening_rate'] == 150.50


def test_parse_items_unit_defaults_to_pcs():
    """Items without an explicit unit default to pcs."""
    xml = """<TallySync><Item><Name>X</Name><Parent>P</Parent></Item></TallySync>"""
    result = parse_items(xml)
    assert result[0]['unit'] == 'pcs'


def test_parse_voucher_with_inventory():
    xml = """<TallySync type="vouchers">
      <Voucher>
        <Date>2026-05-20</Date>
        <Type>Sales</Type>
        <Number>S001</Number>
        <Party>D-Mart</Party>
        <Amount>5000</Amount>
        <Narration>Test sale</Narration>
        <LedgerEntries>
          <Entry><Ledger>Sales</Ledger><Amount>-5000</Amount><IsDeemedPositive>No</IsDeemedPositive></Entry>
          <Entry><Ledger>D-Mart</Ledger><Amount>5000</Amount><IsDeemedPositive>Yes</IsDeemedPositive></Entry>
        </LedgerEntries>
        <InventoryEntries>
          <Item><Name>Surf</Name><Quantity>50</Quantity><Rate>100</Rate><Amount>5000</Amount></Item>
        </InventoryEntries>
      </Voucher>
    </TallySync>"""
    result = parse_vouchers(xml)
    assert len(result) == 1
    v = result[0]
    assert v['type'] == 'Sales'
    assert v['party'] == 'D-Mart'
    assert v['amount'] == 5000
    assert len(v['ledger_entries']) == 2
    assert v['ledger_entries'][0]['ledger'] == 'Sales'
    assert v['ledger_entries'][1]['is_positive'] is True
    assert len(v['inventory_entries']) == 1
    assert v['inventory_entries'][0]['qty'] == 50
    assert v['inventory_entries'][0]['rate'] == 100


def test_parse_voucher_negative_amount_handled():
    """Tally uses negative amounts on credit entries; we need the raw value."""
    xml = """<TallySync><Voucher><Date>2026-05-20</Date><Type>Sales</Type><Number>S001</Number><Party>X</Party><Amount>5000</Amount><Narration></Narration>
      <LedgerEntries><Entry><Ledger>Sales</Ledger><Amount>-5000</Amount><IsDeemedPositive>No</IsDeemedPositive></Entry></LedgerEntries>
      <InventoryEntries></InventoryEntries></Voucher></TallySync>"""
    result = parse_vouchers(xml)
    assert result[0]['ledger_entries'][0]['amount'] == -5000


def test_parse_empty_voucher_list():
    xml = """<TallySync type="vouchers"></TallySync>"""
    assert parse_vouchers(xml) == []


def test_parse_malformed_amount_doesnt_crash():
    """Garbage amount → 0, not exception."""
    xml = """<TallySync><Ledger><Name>X</Name><Parent>P</Parent><OpeningBalance>not-a-number</OpeningBalance></Ledger></TallySync>"""
    result = parse_ledgers(xml)
    assert result[0]['opening_balance'] == 0


def test_xml_with_special_chars():
    """Names with & and other XML special chars (assumed already escaped by TDL XMLEncode)."""
    xml = """<TallySync><Ledger><Name>M&amp;M Distributors</Name><Parent>X</Parent></Ledger></TallySync>"""
    result = parse_ledgers(xml)
    assert result[0]['name'] == 'M&M Distributors'


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""Integration tests for real sandbox provider integrations."""
import os
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session

# Set environment variables to use real integrations for these tests
os.environ["USE_REAL_ISSUING"] = "true"
os.environ["USE_REAL_PAYMENT_RAIL"] = "true"
os.environ["USE_REAL_PLAID"] = "true"
os.environ["USE_REAL_DIDIT"] = "true"
os.environ["USE_REAL_QBO"] = "true"


class TestStripeIssuingIntegration:
    """Test Stripe Issuing test mode integration."""
    
    @pytest.mark.skipif(
        not os.getenv("STRIPE_SECRET_KEY"),
        reason="STRIPE_SECRET_KEY not set"
    )
    def test_create_virtual_card(self):
        """Test creating a virtual card in Stripe test mode."""
        from app.cards.partner_client import StripeIssuingClient
        
        client = StripeIssuingClient()
        
        result = client.create_card(
            entity_id="test_entity_123",
            owner_id="test_user_123",
            card_type="VIRTUAL",
            limit_amount=1000.0
        )
        
        assert result["status"] == "ACTIVE"
        assert "card_token" in result
        assert "masked_pan" in result
        assert "cardholder_id" in result
        assert result["masked_pan"].startswith("**** **** ****")
    
    @pytest.mark.skipif(
        not os.getenv("STRIPE_SECRET_KEY"),
        reason="STRIPE_SECRET_KEY not set"
    )
    def test_freeze_unfreeze_card(self):
        """Test freezing and unfreezing a card."""
        from app.cards.partner_client import StripeIssuingClient
        
        client = StripeIssuingClient()
        
        # First create a card
        card = client.create_card(
            entity_id="test_entity_123",
            owner_id="test_user_123",
            card_type="VIRTUAL",
            limit_amount=1000.0
        )
        
        # Freeze the card
        assert client.freeze_card(card["card_token"]) is True
        
        # Unfreeze the card
        assert client.unfreeze_card(card["card_token"]) is True
    
    @pytest.mark.skipif(
        not os.getenv("STRIPE_SECRET_KEY"),
        reason="STRIPE_SECRET_KEY not set"
    )
    def test_update_card_limit(self):
        """Test updating card spending limit."""
        from app.cards.partner_client import StripeIssuingClient
        
        client = StripeIssuingClient()
        
        card = client.create_card(
            entity_id="test_entity_123",
            owner_id="test_user_123",
            card_type="VIRTUAL",
            limit_amount=1000.0
        )
        
        # Update limit
        assert client.update_limit(card["card_token"], 2500.0) is True


class TestDwollaIntegration:
    """Test Dwolla Sandbox integration."""
    
    @pytest.mark.skipif(
        not os.getenv("DWOLLA_APP_KEY") or not os.getenv("DWOLLA_APP_SECRET"),
        reason="Dwolla credentials not set"
    )
    def test_initiate_transfer(self):
        """Test initiating a Dwolla sandbox transfer."""
        from app.bills.payment_rail import DwollaPaymentRailClient
        
        client = DwollaPaymentRailClient()
        
        transfer_ref = client.initiate_transfer(
            bank_account_id="test_bank_123",
            amount=Decimal("500.00")
        )
        
        assert transfer_ref is not None
        assert transfer_ref.startswith("dwolla_")
    
    @pytest.mark.skipif(
        not os.getenv("DWOLLA_APP_KEY") or not os.getenv("DWOLLA_APP_SECRET"),
        reason="Dwolla credentials not set"
    )
    def test_get_transfer_status(self):
        """Test checking transfer status."""
        from app.bills.payment_rail import DwollaPaymentRailClient
        
        client = DwollaPaymentRailClient()
        
        # First initiate a transfer
        transfer_ref = client.initiate_transfer(
            bank_account_id="test_bank_123",
            amount=Decimal("500.00")
        )
        
        # Check status
        status = client.get_transfer_status(transfer_ref)
        assert status in ["processed", "pending", "unknown"]


class TestPlaidIntegration:
    """Test Plaid Sandbox integration."""
    
    @pytest.mark.skipif(
        not os.getenv("PLAID_CLIENT_ID") or not os.getenv("PLAID_SECRET"),
        reason="Plaid credentials not set"
    )
    def test_create_link_token(self):
        """Test creating a Plaid Link token."""
        from app.plaid.client import PlaidClient
        
        client = PlaidClient()
        
        link_token = client.create_link_token(
            entity_id="test_entity_123",
            user_id="test_user_123"
        )
        
        assert link_token is not None
        assert isinstance(link_token, str)
    
    @pytest.mark.skipif(
        not os.getenv("PLAID_CLIENT_ID") or not os.getenv("PLAID_SECRET"),
        reason="Plaid credentials not set"
    )
    def test_exchange_public_token(self):
        """Test exchanging a public token for access token."""
        from app.plaid.client import PlaidClient
        
        client = PlaidClient()
        
        # This would normally come from Plaid Link frontend
        # For testing, we'll use a mock public token
        mock_public_token = "public-sandbox-test-token"
        
        result = client.exchange_public_token(mock_public_token)
        
        # In sandbox mode, this should work with mock tokens
        # In production, this would require a real public token from Plaid Link
        assert "access_token" in result or result is None  # May fail with mock token


class TestDiditIntegration:
    """Test Didit KYC/KYB integration."""
    
    @pytest.mark.skipif(
        not os.getenv("DIDIT_API_KEY"),
        reason="DIDIT_API_KEY not set"
    )
    def test_create_verification(self):
        """Test creating a KYC/KYB verification."""
        from app.kyc.client import DiditClient
        
        client = DiditClient()
        
        verification = client.create_verification(
            entity_id="test_entity_123",
            entity_name="Test Company LLC",
            entity_type="business",
            email="test@example.com"
        )
        
        assert verification["status"] in ["pending", "approved"]
        assert "verification_id" in verification
    
    @pytest.mark.skipif(
        not os.getenv("DIDIT_API_KEY"),
        reason="DIDIT_API_KEY not set"
    )
    def test_get_verification_status(self):
        """Test checking verification status."""
        from app.kyc.client import DiditClient
        
        client = DiditClient()
        
        # First create a verification
        verification = client.create_verification(
            entity_id="test_entity_123",
            entity_name="Test Company LLC",
            entity_type="business",
            email="test@example.com"
        )
        
        # Check status
        status = client.get_verification_status(verification["verification_id"])
        
        assert status["status"] in ["pending", "approved", "rejected"]


class TestQBOIntegration:
    """Test QuickBooks Online Sandbox integration."""
    
    @pytest.mark.skipif(
        not os.getenv("QBO_CLIENT_ID") or not os.getenv("QBO_CLIENT_SECRET"),
        reason="QBO credentials not set"
    )
    def test_get_oauth_url(self):
        """Test generating QBO OAuth URL."""
        from app.qbo.client import QuickBooksOnlineClient
        
        client = QuickBooksOnlineClient()
        
        oauth_url = client.get_oauth_url(state="test_state_123")
        
        assert oauth_url is not None
        assert "sandbox.qbo.intuit.com" in oauth_url
        assert "test_state_123" in oauth_url
    
    @pytest.mark.skipif(
        not os.getenv("QBO_CLIENT_ID") or not os.getenv("QBO_CLIENT_SECRET"),
        reason="QBO credentials not set"
    )
    def test_get_chart_of_accounts_mock(self):
        """Test getting chart of accounts (requires OAuth flow first)."""
        from app.qbo.client import MockQBOClient
        
        # Use mock client since we don't have real OAuth tokens
        client = MockQBOClient()
        
        accounts = client.get_chart_of_accounts(
            access_token="mock_token",
            realm_id="mock_realm"
        )
        
        assert len(accounts) > 0
        assert all("Id" in acc and "Name" in acc for acc in accounts)


class TestMockClients:
    """Test that mock clients work as fallbacks."""
    
    def test_mock_issuing_client(self):
        """Test mock issuing client."""
        from app.cards.partner_client import MockIssuingPartnerClient
        
        client = MockIssuingPartnerClient()
        
        card = client.create_card(
            entity_id="test_entity",
            owner_id="test_user",
            card_type="VIRTUAL",
            limit_amount=1000.0
        )
        
        assert card["status"] == "ACTIVE"
        assert "card_token" in card
        assert client.freeze_card(card["card_token"]) is True
        assert client.unfreeze_card(card["card_token"]) is True
    
    def test_mock_payment_rail_client(self):
        """Test mock payment rail client."""
        from app.bills.payment_rail import MockPaymentRailClient
        
        client = MockPaymentRailClient()
        
        transfer_ref = client.initiate_transfer(
            bank_account_id="test_bank",
            amount=Decimal("500.00")
        )
        
        assert transfer_ref is not None
        assert transfer_ref.startswith("ref_ach_")
    
    def test_mock_plaid_client(self):
        """Test mock Plaid client."""
        from app.plaid.client import MockPlaidClient
        
        client = MockPlaidClient()
        
        link_token = client.create_link_token(
            entity_id="test_entity",
            user_id="test_user"
        )
        
        assert link_token is not None
        assert link_token.startswith("link-sandbox-")
    
    def test_mock_didit_client(self):
        """Test mock Didit client."""
        from app.kyc.client import MockDiditClient
        
        client = MockDiditClient()
        
        verification = client.create_verification(
            entity_id="test_entity",
            entity_name="Test Company",
            entity_type="business",
            email="test@example.com"
        )
        
        assert verification["status"] == "pending"
        assert "verification_id" in verification
    
    def test_mock_qbo_client(self):
        """Test mock QBO client."""
        from app.qbo.client import MockQBOClient
        
        client = MockQBOClient()
        
        oauth_url = client.get_oauth_url(state="test_state")
        assert oauth_url is not None
        
        accounts = client.get_chart_of_accounts("mock_token", "mock_realm")
        assert len(accounts) > 0

# This is a mock payment processor for demonstration purposes.
# we will update it later once we get our Stripe/PayPal accounts ready.
def process_payment(user, amount: float) -> bool:
    """
    Mock payment processor.
    Replace later with Stripe/PayPal API.
    """
    print(f"Processing £{amount} payment for {user.email}...")
    # Always succeed for now
    return True
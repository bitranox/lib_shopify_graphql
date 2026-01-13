# Shopify App Setup (Dev Dashboard)

This library uses **OAuth 2.0 Client Credentials Grant** for authentication. This is the
authentication method for apps created via the Shopify Developer Dashboard.

## Step 1: Create an App in Dev Dashboard

1. Go to [https://dev.shopify.com/dashboard](https://dev.shopify.com/dashboard)
2. Click **Create an app**
3. Name your app (e.g., "My Integration")
4. Under **Configuration**, add your store as a test store
5. Configure **API access scopes**:
   - `read_products` - for product access
   - `write_products` - for product modifications
   - `read_inventory` - for inventory access
   - `write_inventory` - for inventory modifications
   - Add other scopes as needed for your use case
6. Go to **Client credentials** section
7. Copy the **Client ID** and **Client Secret**

> **Important**: Store the client secret securely - you may not be able to view it again!

## Step 2: Configure Credentials

Create a `.env` file in your project root:

```bash
# .env
SHOPIFY__SHOP_URL=your-store.myshopify.com
SHOPIFY__CLIENT_ID=your_client_id_here
SHOPIFY__CLIENT_SECRET=your_client_secret_here
```

Or set environment variables:

```bash
export SHOPIFY__SHOP_URL=your-store.myshopify.com
export SHOPIFY__CLIENT_ID=your_client_id_here
export SHOPIFY__CLIENT_SECRET=your_client_secret_here
```

## Step 3: Verify Connection

```python
from lib_shopify_graphql import login, logout, ShopifyCredentials, get_config

config = get_config()
credentials = ShopifyCredentials(
    shop_url=config.get("shopify.shop_url"),
    client_id=config.get("shopify.client_id"),
    client_secret=config.get("shopify.client_secret"),
)

session = login(credentials)
print(f"Successfully connected to: {session.info.shop_url}")
logout(session)
```

Or use the CLI health check:

```bash
lib-shopify-graphql health
```

> **Note**: Access tokens obtained via client credentials grant are valid for 24 hours.
> The session will automatically refresh the token when needed.

## Required API Scopes

| Scope | Description |
|-------|-------------|
| `read_products` | Read product information |
| `write_products` | Create, update, delete products |
| `read_inventory` | Read inventory levels |
| `write_inventory` | Adjust inventory levels |
| `read_locations` | Read location information |

## Troubleshooting

### Authentication Failed

1. Verify your `client_id` and `client_secret` are correct
2. Ensure the app is installed on the target store
3. Check that required API scopes are enabled

### Access Denied

1. Verify the app has the required scopes for the operation
2. Check that your store plan supports the API features you're using

### Connection Issues

1. Verify the `shop_url` format: `your-store.myshopify.com` (no `https://`)
2. Check your network connectivity
3. Verify Shopify API status at [status.shopify.com](https://status.shopify.com)

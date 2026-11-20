Business notes for the Olist Brazilian e-commerce database (use these when writing SQL):
- Dates and timestamps are stored as TEXT in 'YYYY-MM-DD HH:MM:SS' format. Use strftime(), date() and julianday() to work with them (e.g. strftime('%Y-%m', order_purchase_timestamp)).
- orders.customer_id is unique per ORDER. customers.customer_unique_id identifies the actual PERSON; use it to count real customers or repeat buyers.
- Revenue means SUM(order_items.price) (freight_value is shipping, not revenue) unless the question says otherwise. Only filter on order_status = 'delivered' when the question explicitly mentions delivered orders, or asks about delivery time or late delivery. For every other question (payments, freight, sellers, categories, order counts, customers), include orders of all statuses and do not add any status filter.
- An order can have several rows in order_items (one per item), order_payments (installments or multiple payment types) and occasionally order_reviews. Aggregate or de-duplicate carefully so joins do not double count.
- Order value as paid by the customer = SUM(order_payments.payment_value) per order.
- Product category names are in Portuguese in products.product_category_name. Use English names by joining category_translation ON products.product_category_name = category_translation.product_category_name. Two categories (pc_gamer, portateis_cozinha_e_preparadores_de_alimentos) have no translation, and some products have no category (NULL).
- Delivery time in days = julianday(order_delivered_customer_date) - julianday(order_purchase_timestamp). Late delivery = order_delivered_customer_date > order_estimated_delivery_date. Delivery dates can be NULL for orders that were not delivered.
- States are 2-letter Brazilian codes (SP, RJ, MG, ...). The geolocation table is not included.
- All monetary values are in Brazilian reais (BRL, R$), not US dollars.

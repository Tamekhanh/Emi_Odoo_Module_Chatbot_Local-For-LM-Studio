import xmlrpc.client

# --- Cấu hình thông số kết nối ---
url = 'http://localhost:8069'
db = 'mydb' # Thay bằng tên database của bạn
username = 'admin'          # Thay bằng username của bạn
password = 'admin'  # Thay bằng password của bạn

try:
    # 1. Xác thực (Authentication)
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    print(f"Successfully authenticated. User ID: {uid}")

    # 2. Kết nối tới đối tượng Model
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    # 3. Truy vấn dữ liệu từ model kms.knowledge.article
    # Lấy các trường: name, body_html, workspace_dimension, tag_ids
    fields_to_fetch = ['name', 'body_html', 'workspace_dimension', 'tag_ids']
    
    # Thực hiện search_read
    articles = models.execute_kw(db, uid, password, 'kms.knowledge.article', 'search_read', [[]], {
        'fields': fields_to_fetch
    })

    # 4. In kết quả ra terminal
    print("\n--- KNOWLEDGE DATA STREAM ---")
    for art in articles:
        print(f"Title: {art['name']}")
        print(f"Dimension: {art['workspace_dimension']}")
        print(f"Tags (IDs): {art['tag_ids']}")
        print(f"Content: {art['body_html']}")
        print("-" * 40)

except Exception as e:
    print(f"Error occurred: {e}")
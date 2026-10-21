# Quy tắc triển khai dự án IoT

- Backend dùng Django REST Framework. Đặt `django_filters.FilterSet` trong `backend/core/filters/`, tách từng filterset theo model và export ở `__init__.py`. Đặt kiểm tra dữ liệu, quyết định nghiệp vụ, đọc payload MQTT và ghi dữ liệu trong `backend/core/serializers/`.
- Các endpoint danh sách dùng `DEFAULT_FILTER_BACKENDS` và `DEFAULT_PAGINATION_CLASS` trong `backend/iot/settings.py`; view khai báo `filterset_class` và `ordering_fields` khi cần. Không tự viết hàm lọc queryset hoặc paginator thay cho cơ chế của DRF/django-filter.
- `backend/core/views/` chỉ khai báo endpoint, quyền truy cập, gọi serializer và trả HTTP response. Không đặt truy vấn, validation, transaction hoặc chuyển trạng thái nghiệp vụ trong view.
- `backend/core/tasks.py` chỉ cấu hình kết nối MQTT, nhận/gửi bản tin và lập lịch Celery; mọi quyết định về nội dung bản tin, sensor, device và history do serializer xử lý.
- Giữ nguyên model và migration hiện có. Chỉ thêm hoặc thay model/field khi người dùng đã cho phép thay đổi cụ thể đó; nếu chưa có phép, nêu rõ lý do rồi hỏi trước khi sửa.
- FE ở chế độ API phải dùng đúng dữ liệu/backend hiện tại. Không gán số đo hoặc trạng thái thiết bị giả khi thiếu dữ liệu.
- Các API nội dung và route FE ở chế độ API yêu cầu Django User đã xác thực bằng SimpleJWT. Đăng ký dùng `get_user_model()` và Django password validators; không tạo model User khác. Màn đăng nhập/đăng ký không hiển thị AppShell hay dữ liệu trước khi xác thực.

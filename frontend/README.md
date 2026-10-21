# IoT Monitoring frontend

Vue 3 + TypeScript + Vite, Vue Router, Pinia. Các route: `/login`, `/register`, `/dashboard`, `/data`, `/history`, `/profile`. Ở chế độ API, lần vào đầu chưa đăng nhập sẽ thấy màn đăng nhập/đăng ký trước mọi nội dung.

Để hiểu cách các file, component và luồng dữ liệu được tổ chức, đọc [Hiểu cấu trúc Vue trong frontend IoT](./VUE_STRUCTURE.md).

## Chạy preview

```bash
cd /home/ducva/Iot/frontend
npm install
npm run dev
```

Mở `http://localhost:5173`. FE mặc định gọi API tại `http://localhost:8000/api/v1`.
Nếu backend chưa chạy, trang báo lỗi kết nối và không hiển thị số đo giả. Xem
[hướng dẫn backend](../backend/README.md) để chạy Django, Celery worker, Beat
và provision sensor/LED.

```bash
npm run build
npm run preview
```

Preview production mặc định ở `http://localhost:4173`. Khi deploy static, cấu hình fallback các route tới `index.html`.

## Cấu hình API và chế độ mock

Tạo `frontend/.env.local`:

```dotenv
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_REFRESH_MS=4000
VITE_TRENDS_REFRESH_MS=4000
VITE_COMMAND_POLL_MS=750
VITE_COMMAND_CLIENT_TIMEOUT_MS=10000
```

FE đã chọn API thật theo mặc định; `.env.local` chỉ cần khi đổi địa chỉ API.
`VITE_DATA_SOURCE=mock` bật dữ liệu mẫu để xem UI khi chưa chạy backend.
Khởi động lại dev server hoặc build lại sau khi đổi biến môi trường.

Adapter thật theo [backend hiện tại](../backend/README.md): các danh sách `sensors/`,
`sensor-data/`, `devices/`, `device-history/`, control và polling.
Đăng ký qua `/register` dùng Django
User hiện cấu hình; `/login` nhận token từ SimpleJWT. Mọi request nội dung gửi
Bearer access token. Token được giữ trong `sessionStorage` của tab, xác minh
qua `/api/auth/me/` khi mở lại trang và refresh khi hết hạn; mật khẩu không được
lưu. Khi đăng xuất, màn nội dung đóng ngay. Chế độ mock là bản xem UI cho phát
triển và không dùng backend xác thực. Khi backend trả lỗi, FE hiển thị lỗi đó.
URL của FE giữ `page` và `page_size`; HTTP adapter chuyển thành `limit` và
`offset` theo `LimitOffsetPagination` của DRF.

Data Search gửi `value` để tìm đúng số đo (ví dụ
`type=TEMPERATURE&value=28.5`); backend hiện hỗ trợ tham số này. Time được
chuyển thành `from/to` UTC của phút hoặc giây đã chọn; không gửi `type=TIME`
tới backend.

Firmware gửi Light dưới dạng ADC, vì vậy FE ở chế độ API hiển thị **ADC** ở
card và biểu đồ. Firmware không gửi thời điểm đo; `measured_at=null` và
`created_at` là giờ backend nhận bản tin. Thiết bị chưa có phản hồi trạng
thái live sẽ hiển thị **Unconfirmed**. Dashboard chỉ hiển thị số đo đã lưu; thiếu dữ liệu được để trống, không tạo số đo bằng 0 hay suy diễn lỗi DHT11.

Profile ở chế độ API lấy `full_name`, `student_id` và email từ `/api/auth/me/`. Bấm tên hoặc Mã sinh viên để sửa hai giá trị đầu qua PATCH cùng endpoint; nút Logout chỉ ở Profile. Email và username không đổi qua form này. `src/config/profile.ts` chỉ chứa thông tin mẫu của chế độ mock và các URL công khai; URL chưa có được hiển thị disabled.

## Mock hoạt động như một backend

- Seed hơn 1.000 số đo trong 24 giờ và 100 lịch sử lệnh, có SUCCESS/FAILED/TIMEOUT.
- Mock giữ nguyên dữ liệu mẫu: không tự sinh số đo, không tự thêm lịch sử hoặc đổi trạng thái thiết bị. Chế độ mock không polling nền. Khi chuyển `VITE_DATA_SOURCE=api`, polling tự bật và lấy dữ liệu mới từ backend mà không reload trang.
- Điều khiển tạo PENDING, xác nhận SUCCESS sau khoảng 1,4 giây; cùng idempotency key trả lại cùng lệnh. State đã xác nhận và History cùng dùng một database.
- History có cột User giữa Device và Action, lấy từ `user.username`. Mock cung cấp username mẫu; API thật trả username của người đã gửi lệnh qua JWT. Bản tin điều khiển bên ngoài không tự tạo History/User giả.
- Database lưu trong localStorage (`iot-demo-database-v1`) của trình duyệt/origin hiện tại. Có fallback bộ nhớ nếu storage bị chặn. Mỗi tab giữ một bản mô phỏng riêng; đây không phải server đồng bộ giữa nhiều client.
- Muốn seed lại: xóa key trên trong DevTools → Application → Local Storage rồi mở lại trang.
- Data chọn Temperature/Humidity/Light rồi nhập giá trị số vào Search để tìm đúng số đo, kết hợp AND với loại cảm biến. All Types tìm giá trị trên cả ba loại. Search chấp nhận dấu thập phân chấm hoặc phẩy; không tìm ID/code/name.
- Data không có ô From/To hoặc khoảng thời gian riêng. Chọn Time trong Type để nhập text, có thể copy trực tiếp từ cột Date & Time (ví dụ `21 Oct 2026, 12:34:56`) theo timezone trình duyệt; vẫn hỗ trợ `2026-10-21T12:34:56`. Nhập tới phút sẽ tìm trong phút đó, nhập giây sẽ tìm trong giây đó. Các tham số `from/to` cũ trên URL Data bị bỏ qua; khoảng thời gian query API được tạo từ Search khi chọn Time.
- History mock giữ Search ID/command UUID và TIMEOUT. API thật dùng History ID
  dạng số và ba trạng thái của model: PENDING/SUCCESS/FAILED. Bộ lọc khoảng
  thời gian trên History vẫn hoạt động với API thật.
- Filter chỉ áp dụng khi bấm Filter, về trang 1; Reset xóa filter. Sắp xếp/phân trang giữ các điều kiện đã áp dụng.

## Cấu trúc tái sử dụng

```text
src/
  app/                  # Router và AppShell/sidebar dùng chung
  api/                  # IoTApi selector, HTTP adapter, mock database
  components/common/    # Header, icon, badge, pagination, thông báo
  components/dashboard/ # SensorCard, SensorTrendsChart, DeviceCard
  components/listing/   # ListingPage, QueryFilters, DataTable
  composables/          # Polling, list query, theo dõi command
  stores/               # Intent control giữ trong sessionStorage
  config/               # Environment và Profile
  types/                # DTO dùng chung theo REST contract
  views/                # Bốn route và NotFound
```

Document luôn cố định trong `100dvh`, không cuộn toàn trang. Dashboard/chart co theo phần chiều cao còn lại. Data/History cố định 10 bản ghi mỗi trang (trang cuối hoặc kết quả lọc có thể ít hơn); không tự đổi page_size theo viewport. Hàng bảng dùng layout gọn để giữ 10 bản ghi trong chiều cao màn hình desktop. Header/footer/phân trang luôn ở trong viewport. Profile dùng grid co theo chiều cao. Mobile có navigation drawer và bảng cuộn ngang. Màn hình rất thấp hoặc backend có nhiều thiết bị vẫn cần cuộn trong vùng nội dung tương ứng.

Dashboard polling không chồng request, bỏ response cũ, dừng khi rời route/tab ẩn, refresh khi tab hiện lại. Data và History không tự động refresh theo thời gian hoặc khi quay lại tab; chỉ tải khi mở trang, lọc/reset, đổi trang, đổi số dòng, sắp xếp hoặc thử lại. Background refresh của Dashboard giữ dữ liệu đã có; loading/error/empty được xử lý riêng. Control không tự kết luận TIMEOUT khi mất mạng: giữ intent/idempotency key, cho kiểm tra lại, và nối lại polling khi quay lại Dashboard.
Dashboard lấy sensor ACTIVE từ `sensors/?status=ACTIVE` và số đo mới nhất mỗi loại từ `sensor-data/?type=...&sensor_status=ACTIVE&ordering=-created_at,-id&limit=1` theo `VITE_REFRESH_MS`. Biểu đồ phân trang `sensor-data/?sensor_status=ACTIVE&ordering=-created_at,-id` theo `VITE_TRENDS_REFRESH_MS`, rồi gom 20 thời điểm đo mới nhất, kể cả khi dữ liệu cũ hơn 24 giờ.

## Nguồn thiết kế và giới hạn

Các file `dashboard.html`, `data_sensor.html`, `history_action.html` được giữ nguyên làm nguồn CSS Figma; chúng không phải trang HTML có thể chạy. Palette, font Inter, sidebar, cards, chart, filters và bảng được chuyển thành component responsive thay cho tọa độ absolute của frame.

`profile.html` rỗng, nên Profile được dựng từ `../docs/frontend/01-ui-specification.md` và cùng design token. Chưa có screenshot/asset gốc để đối chiếu pixel-perfect. Icon dùng Lucide; biểu đồ SVG render từ số đo, có tooltip, legend và ba trục đơn vị độc lập, giữ khoảng trống null.

## Kiểm tra

```bash
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Có thể dùng Chromium có sẵn bằng biến `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. E2E kiểm tra routes, viewport, filter/sort/pagination, cập nhật không reload và control xuất hiện trong History. Kết quả lỗi/screenshot được lưu trong `test-results/` (không commit).

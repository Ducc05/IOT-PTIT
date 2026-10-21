# IoT backend — Django REST Framework + Celery

Backend dùng `core/models/`, `core/serializers/`, `core/views/` và `core/tasks.py`.
Validation, lọc dữ liệu, dashboard, xử lý payload MQTT và quyết định điều khiển
nằm trong `core/serializers/`. View chỉ nối HTTP với serializer; Celery task chỉ
lập lịch và giữ kết nối/truyền bản tin MQTT. Quy tắc này nằm trong `../AGENTS.md`.
Giữ nguyên toàn bộ model/field và migration `core/0001_initial.py` của project.
Không có app Controller/Notification mới, service/selector layer hay MQTT worker riêng.

## Contract lấy từ firmware

Nguồn: `../mqtt/main.cpp`, bản đã cập nhật ngày 13/10/2026.

| Topic | Payload / xử lý |
| --- | --- |
| `esp32/sensor/data` | `success`, `temperature`, `humidity`, `light`; lỗi DHT11: `success=false`, `error=DHT11_READ_FAILED`, `light` |
| `esp32/status` | ESP32 ONLINE/OFFLINE; ONLINE retained không có timestamp, không chứng minh dữ liệu còn mới |
| `esp32/led1/status`, `esp32/led2/status` | `device`, `state`; cập nhật Device đã provision |
| `esp32/led1/history`, `esp32/led2/history` | action/previous_state/state_after/changed/control_status/reason; xác nhận intent đang chờ trong task |
| `esp32/led/history` | Lịch sử thao tác ALL bên ngoài; validate cấu trúc rồi log; không tự tạo User/History |
| `esp32/led1/control`, `esp32/led2/control` | Backend gửi text `ON` hoặc `OFF`, retain=false |

`light` là ADC 12-bit (0…4095), **không phải lux**. Registry phải đặt unit `ADC`.
Temperature: °C, giới hạn parser 0…50 theo DHT11; Humidity: %, 0…100.
[DHT11 specifications (Adafruit)](https://learn.adafruit.com/dht?view=all).

## MQTT và Celery là hai kết nối khác nhau

- MQTT: broker trên Windows, port **1884**, host lấy từ firmware/cấu hình `MQTT_HOST`.
- Celery: một broker AMQP/RabbitMQ riêng, thường port **5672**, đặt `CELERY_BROKER_URL`.
- Result backend: app `django_celery_results` đã có trong project, dùng database hiện tại.
- Backend đọc `.env` khi khởi động; không cần `source ~/.bashrc` để có cấu hình.
- `.env.example` chỉ có placeholder; credentials thật chỉ nằm trong `.env` bị Git ignore.

Thiết lập trong `backend/.env`:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/iot_db
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
MQTT_HOST=WINDOWS_IP
MQTT_PORT=1884
MQTT_USERNAME=YOUR_MQTT_USER
MQTT_PASSWORD=YOUR_MQTT_PASSWORD
MQTT_CLIENT_ID=iot-celery-reader
MQTT_TLS_ENABLED=false
MQTT_SENSOR_IDS={}
MQTT_DEVICE_IDS={}
CELERY_BROKER_URL=amqp://USER:PASSWORD@localhost:5672//
```

Không đổi host thành localhost để né lỗi khi broker Windows chưa mở. WSL và ESP
phải kết nối tới địa chỉ Windows truy cập được và listener/firewall port 1884.
Không đọc password từ firmware ở mỗi task; cấu hình runtime được nạp từ `.env`.

## Khởi tạo và chạy

```bash
cd /home/ducva/Iot/backend
uv sync --locked
uv run python manage.py check
```

Nếu là database mới, chạy migration rồi tạo registry cho firmware:

```bash
uv run python manage.py migrate
uv run python manage.py seed_iot
uv run python manage.py createsuperuser
```

Với database đã migrate, chỉ chạy `seed_iot` khi muốn provision registry. Command
này tạo ba sensor ACTIVE và hai Device tên LED1/LED2 nếu chưa có; không overwrite
state/history/sensor unit. Nếu có nhiều sensor ACTIVE cùng type hoặc LIGHT đang
unit lux, command dừng để sửa có chủ đích qua admin/API, không tự sửa dữ liệu.

Mapping mặc định: một Sensor ACTIVE cho mỗi type, Device có name chính xác
LED1/LED2. Nếu muốn đổi tên Device, cấu hình ID trước, ví dụ:

```dotenv
MQTT_SENSOR_IDS={"TEMPERATURE":1,"HUMIDITY":2,"LIGHT":3}
MQTT_DEVICE_IDS={"LED1":1,"LED2":2}
```

Đây là ví dụ ID; dùng ID thật trong database, không sao chép số khi registry khác.

Chạy ba terminal:

```bash
uv run python manage.py runserver 127.0.0.1:8000
```

```bash
uv run celery -A iot worker -Q mqtt --concurrency=1 -l INFO
```

```bash
uv run celery -A iot beat -l INFO
```

Chỉ chạy một Beat và một Celery child dành cho queue `mqtt`. Task
`core.tasks.read_mqtt_data` chạy mỗi **5 giây**. Subscriber Paho được tạo trong
Celery child ở task đầu tiên và giữ kết nối/network loop giữa các task; callback
chỉ đẩy message vào queue có giới hạn. Task drain queue, validate bằng DRF
serializer và transaction rồi lưu SensorData. Một PostgreSQL advisory lock ngăn
child thứ hai chiếm subscription. Không khởi tạo MQTT connection trong HTTP.

Đây là lựa chọn phù hợp với firmware gửi mỗi 2 giây và publish QoS0. Mở rồi đóng
subscriber mỗi 5 giây sẽ có khoảng trống. QoS0 không replay khi process chết,
queue đầy hoặc subscription chưa có; `clean_session=False` không biến QoS0 thành
bảo đảm không mất dữ liệu. [PubSubClient API](https://pubsubclient.knolleary.net/api),
[Paho client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html).

## API

Swagger UI: `/docs` (also accepts `/docs/`); OpenAPI schema: `/api/schema/`.
Swagger groups API v1 operations by the Sensors, Sensor Data, Devices, and
Device History tags.

| Endpoint | Hành vi |
| --- | --- |
| `/api/v1/sensors/` | ModelViewSet; đọc và ghi đều cần JWT |
| `/api/v1/sensor-data/` | ReadOnlyModelViewSet; FilterSet theo name/type/sensor_status/value/from/to, OrderingFilter theo created_at/value/id |
| `/api/v1/devices/` | ModelViewSet; current_state chỉ đọc, MQTT status cập nhật state |
| `/api/v1/devices/{id}/control/` | POST cần JWT: action TURN_ON/TURN_OFF + idempotency_key; trả 202 PENDING |
| `/api/v1/device-history/` | ReadOnlyModelViewSet; FilterSet theo device/action/status/from/to, search ID, OrderingFilter theo created_at |
| `/api/v1/device-history/{id}/` | Đọc kết quả bằng History PK, kể cả PENDING/FAILED |
| `/api/auth/register/` | Tạo tài khoản qua Django User hiện cấu hình và cấp access/refresh token SimpleJWT |
| `/api/auth/token/`, `/api/auth/token/refresh/` | SimpleJWT; POST username/password, rồi Bearer access token |
| `/api/auth/me/` | GET cần JWT trả hồ sơ gồm username, email, `full_name`, `student_id`, `avatar`; POST cần JWT cập nhật đầy đủ `full_name`, `student_id`, `email` của chính người đăng nhập, có thể kèm file `avatar` bằng multipart |

Mọi endpoint `/api/v1/` yêu cầu Bearer access token; không trả nội dung IoT cho
khách chưa đăng nhập. Đăng ký kiểm tra mật khẩu theo Django password validators,
không tạo User model khác. Migration `core.0003` bổ sung `full_name` và `student_id`
cho `core.User`; `student_id` có thể để trống và phải duy nhất khi được nhập.
Dự án đã cấu hình `AUTH_USER_MODEL=core.User`
(kế thừa Django `AbstractUser`); endpoint đăng ký dùng `get_user_model()` để tạo
đúng tài khoản này.

Các endpoint danh sách dùng `DjangoFilterBackend`, `OrderingFilter` và
`LimitOffsetPagination` từ DRF theo cấu hình `REST_FRAMEWORK`. Tham số phân trang
API là `limit` và `offset` (mặc định 15 bản ghi); FE đổi số trang và số dòng mỗi
trang thành hai tham số này tại HTTP adapter.

Dashboard và bảng dữ liệu dùng `created_at` là thời gian backend nhận message.
Migration `core.0002` chuyển thời gian nhận của dữ liệu cũ sang `created_at` trước khi
xóa cột `recorded_at`. Với MQTT mới, serializer ghi thời điểm nhận vào `created_at`.
Firmware không có measured_at, nên API trả measured_at=null, không bịa giờ đo.
Các trường API như device_code/controller_id/type được derive từ mapping/firmware,
không phải field mới trong database. `state_confirmed_at` và `late_response` không
được persist trong schema hiện tại, API trả null khi không biết.

History.user bắt buộc nên control yêu cầu user thật đã xác thực. Không có actor
giả cho message MQTT do thao tác từ client/thiết bị khác. History API command_id
là chuỗi History PK dùng để polling HTTP; **không phải command_id trên firmware**.

## Các nhánh xử lý dữ liệu

- `success=true` với subset readings không rỗng: lưu đúng số readings có mặt.
- DHT11 lỗi nhưng light hợp lệ: chỉ lưu Light; không tạo Temperature/Humidity=0.
- Thiếu flag/schema, giá trị null/bool/string/NaN/Infinity, ngoài giới hạn, JSON
  key trùng hoặc field lạ: từ chối payload; không lưu một nửa batch.
- Sensor INACTIVE, chưa provision, unit sai hoặc mapping mơ hồ: reject toàn batch;
  không tự tạo Sensor/Device từ telemetry.
- Sensor thay thế: deactivate record cũ, tạo record mới cùng type; giữ FK readings
  cũ. API chặn đổi type/unit khi sensor có dữ liệu và chặn xóa resource có history.
- Rename LED cần mapping ID trước; không silently đổi topic.
- Lỗi DB: giữ message trong queue in-memory cho task sau nếu process còn sống.
  QoS>=1 chỉ ACK sau xử lý và đúng connection generation; firmware data/history
  là QoS0 nên không có application ACK/replay bền vững.
- Các message sensor có cùng giá trị vẫn là số đo khác nhau. Firmware không có
  message_id; không dedup bằng hash và không tuyên bố exactly-once.

Lỗi DHT hiện tại được ghi log có giới hạn theo transition. Payload thành công
có đủ cả Temperature/Humidity mới xóa lỗi DHT. Danh sách số đo chỉ chứa dữ liệu
đã lưu, nên Dashboard suy ra trạng thái thiếu dữ liệu từ thời điểm nhận mới nhất;
không suy diễn lỗi DHT từ một khoảng trống dữ liệu.

## Điều khiển và các giới hạn của firmware hiện tại

View lock Device, chỉ nhận một PENDING/device; idempotency scoped theo user/key
qua task identity/result có sẵn. Queue send sau commit. Nếu AMQP publish lỗi,
History chuyển FAILED và API trả lỗi có ID để tra cứu; không xác nhận SUCCESS.
Task gửi ON/OFF qua publisher ngắn hạn, đợi **history phản hồi** cùng topic/action
trong deadline, không coi PUBACK hay retained LED status là kết quả command.
Task quá hạn không publish lại; publisher bị đóng khi kết thúc để không replay
hàng đợi gửi của nó sau deadline. SUCCESS/FAILED terminal không bị đổi bởi reply
đến trễ. Một phản hồi hợp lệ đầu tiên thắng các phản hồi mâu thuẫn sau đó.

Schema chỉ có PENDING/SUCCESS/FAILED. Khi timeout, dùng FAILED với kết quả task
`DEVICE_RESPONSE_TIMEOUT`; không tự thêm TIMEOUT field/choice. Last-known state
cập nhật từ status hợp lệ của firmware, không set ON ngay khi HTTP/publish nhận.

Các giới hạn không thể khắc phục chỉ bằng views/serializers:

1. Không có message_id/command_id/boot ID/sequence/timestamp trong firmware.
   Reply cũ cùng action đến trong cửa chờ mới, command của client bên ngoài cùng
   topic, hoặc packet trạng thái đảo thứ tự không thể correlate tuyệt đối.
2. Firmware không kiểm expires_at; backend không thu hồi được command đã tới
   broker/ESP. Không bảo đảm thực thi vật lý đúng một lần hay hết hạn end-to-end.
3. Idempotency metadata nằm trong Celery TaskResult, hết cửa sổ khi result bị
   cleanup (mặc định 24 giờ); không hứa key có hiệu lực suốt lịch sử.
4. Không có state-confirmation timestamp/null state trong Device, hay Notification
   entity. Các capability cần field/model mới phải được người dùng duyệt riêng.

Không dùng baseline `iot/v1/...` trong docs cũ để nhận firmware `esp32/...` này.
Không có backfill/durable sensor inbox/threshold automation hay email tự phát.

## Kiểm thử

Các test không dùng database phát triển. Cần PostgreSQL test và các broker test
riêng; tên/port dưới đây chỉ là ví dụ. `iot.test_settings` yêu cầu URL explicit.

```bash
IOT_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:55442/iot_test \
  uv run python manage.py test core.tests --settings=iot.test_settings --noinput
```

Để chạy MQTT/Celery integration: broker MQTT riêng ở 127.0.0.1:28884 (anonymous
chỉ trong fixture), AMQP riêng 127.0.0.1:56793, rồi:

```bash
IOT_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:55442/iot_test \
IOT_TEST_CELERY_BROKER_URL=amqp://USER:PASSWORD@127.0.0.1:56793// \
IOT_TEST_MQTT=1 IOT_TEST_CELERY=1 \
  uv run python manage.py test core.tests --settings=iot.test_settings --noinput
```

Suite kiểm tra payload thiếu/thừa/lỗi, atomic batch, mapping, preserving schema,
CRUD/auth, terminal late reply, concurrent keys/PENDING, persistent subscriber,
PostgreSQL locking và Celery worker+Beat 5s với firmware emulator. Passing fixture
không chứng minh broker Windows/ESP32 vật lý đã chạy; xác minh live riêng khi bật.

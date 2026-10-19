# MQTT broker (Mosquitto)

Thư mục này chứa cấu hình MQTT broker dùng cho hệ thống IoT. Broker lắng nghe
MQTT TCP tại cổng `1883` và yêu cầu đăng nhập bằng tài khoản trong
`password.txt`.

> Cấu hình hiện tại chỉ phù hợp để phát triển trong mạng tin cậy: chưa bật TLS
> và chưa có ACL theo topic. Không mở trực tiếp cổng `1883` ra Internet.

## Thành phần

| Tệp | Mục đích |
| --- | --- |
| `mosquitto.conf` | Cấu hình Mosquitto: listener cổng `1883` và tệp mật khẩu. |
| `password.txt` | Cơ sở dữ liệu mật khẩu đã băm của Mosquitto. Không phải mật khẩu dạng rõ. |
| `.env` | Cấu hình kết nối cho Backend/client khi phát triển cục bộ (không commit). |

## Chạy ở máy cục bộ

### 1. Cài công cụ

Trên Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

### 2. Tạo hoặc đặt lại mật khẩu

Chạy trong thư mục này để đường dẫn tương đối `password.txt` trong cấu hình
được đọc đúng:

```bash
cd /home/ducva/Iot/mqtt
mosquitto_passwd -c password.txt admin
```

Lệnh sẽ yêu cầu nhập mật khẩu hai lần. Tùy chọn `-c` tạo lại tệp và **xóa các
tài khoản cũ**; chỉ dùng khi khởi tạo hoặc chủ động đặt lại tệp. Để thêm người
dùng mà giữ các tài khoản hiện có, bỏ `-c`:

```bash
mosquitto_passwd password.txt ten_nguoi_dung
```

Không đưa `password.txt` hoặc mật khẩu rõ vào Git, mã nguồn, log hay file môi
trường của frontend.

### 3. Khởi động broker

```bash
cd /home/ducva/Iot/mqtt
mosquitto -c mosquitto.conf -v
```

Giữ terminal này chạy trong lúc phát triển. Tham số `-v` in log kết nối và
publish/subscribe ra terminal. Dừng broker bằng `Ctrl+C`.

## Chạy bằng Docker

Nếu đã có Docker, chạy từ thư mục `mqtt`:

```bash
cd /home/ducva/Iot/mqtt
docker run --rm --name iot-mosquitto \
  --user "$(id -u):$(id -g)" \
  -p 1883:1883 \
  -v "$PWD:/mosquitto/config:ro" \
  eclipse-mosquitto:2 \
  mosquitto -c /mosquitto/config/mosquitto.conf -v
```

`--user` giúp Mosquitto trong container đọc được `password.txt` có quyền truy
cập hạn chế trên máy host. `--rm` sẽ xóa container khi dừng, còn cấu hình và
tệp mật khẩu vẫn nằm trong thư mục hiện tại. Nếu cổng `1883` đã được một
Mosquitto khác sử dụng, dừng tiến trình đó hoặc đổi phần bên trái của ánh xạ
cổng, ví dụ `-p 1884:1883`.

## Kiểm tra kết nối

Mở một terminal khác và nạp cấu hình client từ `.env`:

```bash
cd /home/ducva/Iot/mqtt
set -a && . ./.env && set +a
```

Đăng ký nhận toàn bộ message của dự án:

```bash
mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
  -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t 'iot/v1/devices/#' -q 1 -v
```

Trong terminal thứ ba, gửi một bản tin cảm biến mẫu. Terminal subscriber phải
in ra topic và payload vừa gửi.

```bash
mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
  -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t 'iot/v1/devices/ESP32_01/sensors/data' -q 1 \
  -m '{"schema_version":1,"message_id":"manual-test-001","controller_id":"ESP32_01","measured_at":"2026-09-05T00:00:00Z","readings":[{"sensor_code":"TEMP_01","type":"TEMPERATURE","value":28.6,"unit":"°C"}]}'
```

Xóa biến sau khi kiểm tra xong:

```bash
unset MQTT_HOST MQTT_PORT MQTT_USERNAME MQTT_PASSWORD MQTT_TLS_ENABLED
```

## Cấu hình client

Tệp [`.env`](.env) đã đặt sẵn tài khoản phát triển `admin` với mật khẩu `123`:

```env
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USERNAME=admin
MQTT_PASSWORD=123
MQTT_TLS_ENABLED=false
```

Mosquitto **không tự đọc `.env`**. Broker xác thực bằng `password.txt`; tệp
`.env` chỉ để Backend hoặc MQTT client nạp host, port và credential. Với shell,
có thể nạp tệp trước khi chạy client:

```bash
cd /home/ducva/Iot/mqtt
set -a && . ./.env && set +a
```

Sau đó dùng `"$MQTT_USERNAME"` và `"$MQTT_PASSWORD"` trong `mosquitto_sub` /
`mosquitto_pub`, hoặc cấu hình ứng dụng Backend để đọc các biến môi trường này.
Tệp `.env` và `password.txt` đã được liệt kê trong `.gitignore`. Tài khoản
`admin` / `123` chỉ dùng ở máy phát triển; thay mật khẩu trước khi triển khai.

ESP32/ESP8266 phải dùng địa chỉ IP LAN của máy đang chạy broker (ví dụ
`192.168.x.x`), không dùng `127.0.0.1`; địa chỉ loopback trên ESP là chính ESP.
Khi dùng Docker với `-p 1884:1883`, client trên máy host dùng cổng `1884`, còn
client trong cùng mạng Docker dùng cổng nội bộ `1883`.

## Topic và quy ước message

Các topic chuẩn hóa của ứng dụng:

| Luồng | Topic | Publisher → subscriber | QoS | Retain | Payload mẫu |
| --- | --- | --- | ---: | --- | --- |
| Dữ liệu cảm biến | `esp32/sensor/data` | ESP32 → Backend | 1 | Không | `{"temperature": 28.5, "humidity": 70, "light": 1024}` |
| Trạng thái ESP32 | `esp32/status` | ESP32 → Backend | 1 | Có | `{"device":"ESP32","status":"ONLINE","ip":"192.168.1.10"}` |
| Lệnh điều khiển LED | `esp32/led/<id>/control` | Backend → ESP32 | 1 | Không | `ON` hoặc `OFF` |
| Lệnh điều khiển All LED | `esp32/led/all/control` | Backend → ESP32 | 1 | Không | `ON` hoặc `OFF` |
| Trạng thái LED (Reported) | `esp32/led/<id>/status` | ESP32 → Backend | 1 | Có | `{"device":"LED1","state":"ON"}` |

### Quy trình điều khiển (State Confirmation Flow)
1. Backend gửi lệnh `ON` hoặc `OFF` tới topic `esp32/led/<id>/control`.
2. ESP32 nhận lệnh, điều khiển chân GPIO tương ứng và publish trạng thái thực tế lên `esp32/led/<id>/status`.
3. Backend theo dõi topic `esp32/led/<id>/status`:
   - Nếu trạng thái khớp với trạng thái yêu cầu trước thời hạn timeout ➔ Xác nhận lệnh thành công (`SUCCESS`).
   - Nếu quá thời hạn timeout mà không nhận được trạng thái ➔ Đánh dấu lệnh thất bại (`FAILED`).

## Lưu ý trước khi triển khai production

- Bật TLS và dùng cổng TLS riêng; không truyền credential MQTT qua mạng công
  cộng bằng kết nối không mã hóa.
- Tạo credential riêng cho Backend và từng thiết bị, sau đó giới hạn quyền bằng
  ACL đúng các topic được phép publish/subscribe.
- Chỉ cho phép Backend giao tiếp với broker; web frontend không được dùng
  credential của Backend để kết nối trực tiếp.
- Giới hạn kích thước payload, tần suất publish và theo dõi reconnect/publish
  failure của client.

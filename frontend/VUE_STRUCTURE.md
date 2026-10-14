# Hiểu cấu trúc Vue trong frontend IoT

Tài liệu này giải thích cách Vue tổ chức giao diện bằng chính các file trong dự án. Bạn có thể đọc lần lượt rồi bấm vào đường dẫn để mở code tương ứng.

Vue tổ chức giao diện thành những phần nhỏ gọi là **component**. Mỗi component đảm nhiệm một phần: sidebar, bảng, bộ lọc, phân trang hoặc một card cảm biến. Các component được ghép thành trang; router chọn trang cần hiển thị theo URL.

## Mục lục

1. [Luồng khởi động ứng dụng](#1-luồng-khởi-động-ứng-dụng)
2. [Cấu trúc một file Vue](#2-cấu-trúc-một-file-vue)
3. [Vai trò các thư mục](#3-vai-trò-các-thư-mục)
4. [Cách Data và History tái sử dụng giao diện](#4-cách-data-và-history-tái-sử-dụng-giao-diện)
5. [Component trao đổi dữ liệu như thế nào](#5-component-trao-đổi-dữ-liệu-như-thế-nào)
6. [Luồng xử lý khi bấm Filter](#6-luồng-xử-lý-khi-bấm-filter)
7. [Pinia và trạng thái dùng chung](#7-pinia-và-trạng-thái-dùng-chung)
8. [Nên mở file nào khi cần sửa](#8-nên-mở-file-nào-khi-cần-sửa)

## 1. Luồng khởi động ứng dụng

```text
index.html
└── main.ts                  Khởi tạo ứng dụng Vue
    └── App.vue              Component gốc
        └── AppShell.vue     Khung giao diện chung
            ├── Sidebar      Logo và các liên kết điều hướng
            └── RouterView   Vị trí hiển thị trang theo URL
                ├── DashboardView.vue
                ├── SensorDataView.vue
                ├── DeviceHistoryView.vue
                └── ProfileView.vue
```

Các nhánh bên dưới `RouterView` là những trang có thể được chọn. Với mỗi URL hiện tại, router hiển thị trang tương ứng tại vị trí đó.

### `index.html`: nơi đặt ứng dụng

[index.html](./index.html) có phần sau:

```html
<div id="app"></div>
<script type="module" src="/src/main.ts"></script>
```

`#app` là vị trí Vue gắn giao diện vào. Script `main.ts` bắt đầu quá trình khởi tạo.

### `main.ts`: khởi tạo Vue và các thư viện

Trong [src/main.ts](./src/main.ts):

```ts
createApp(App)
  .use(createPinia())
  .use(router)
  .mount('#app')
```

| Lệnh | Ý nghĩa |
|---|---|
| `createApp(App)` | Tạo ứng dụng từ component gốc `App.vue` |
| `.use(createPinia())` | Cài công cụ quản lý trạng thái dùng chung |
| `.use(router)` | Cài cơ chế chọn trang theo URL |
| `.mount('#app')` | Hiển thị ứng dụng vào phần tử có ID `app` |

File này cũng nạp font Inter và CSS chung.

### `App.vue` và `AppShell.vue`: ghép khung giao diện

[App.vue](./src/App.vue) hiển thị [AppShell.vue](./src/app/AppShell.vue).

Trong `AppShell.vue`, sidebar được viết trực tiếp trong khung chung. Phần nội dung chính có:

```vue
<main id="main-content" class="main-content">
  <RouterView />
</main>
```

Vì sidebar thuộc khung chung, cả bốn trang đều sử dụng cùng một sidebar.

### `router.ts`: chọn trang theo URL

[src/app/router.ts](./src/app/router.ts) khai báo các route:

| URL | Component trang |
|---|---|
| `/` | Chuyển đến `/dashboard` |
| `/dashboard` | `DashboardView.vue` |
| `/data` | `SensorDataView.vue` |
| `/history` | `DeviceHistoryView.vue` |
| `/profile` | `ProfileView.vue` |
| URL không khớp | `NotFoundView.vue` |

`RouterLink` là liên kết chuyển route. `RouterView` là vị trí đặt trang được chọn. Khi bấm History ở sidebar, URL chuyển sang `/history` và Vue thay nội dung trong `RouterView` bằng trang History.

## 2. Cấu trúc một file Vue

File `.vue` thường được gọi là **Single File Component**, nghĩa là một file có thể chứa logic, giao diện và CSS của một component.

| Phần | Công việc |
|---|---|
| `<script setup>` | Import component, khai báo dữ liệu, viết hàm xử lý |
| `<template>` | Mô tả giao diện bằng cú pháp gần với HTML |
| `<style>` | Viết CSS cho giao diện |

Không phải component nào cũng cần có đủ cả ba phần. Dự án này dùng CSS chung trong [styles.css](./src/styles.css), nên nhiều file chỉ có script và template.

Ví dụ dưới đây chỉ để minh họa cơ chế Vue:

```vue
<script setup lang="ts">
import { ref } from 'vue'

const temperature = ref(26)

function increase() {
  temperature.value += 1
}
</script>

<template>
  <p>Nhiệt độ: {{ temperature }} °C</p>
  <button @click="increase">Tăng nhiệt độ</button>
</template>

<style scoped>
p {
  color: #004ac6;
}
</style>
```

### Những cú pháp cần hiểu trước

- `lang="ts"`: phần script dùng TypeScript.
- `ref(26)`: tạo dữ liệu mà Vue theo dõi, gọi là dữ liệu reactive.
- `{{ temperature }}`: hiển thị giá trị lên giao diện.
- `@click="increase"`: gọi hàm khi người dùng bấm nút.
- `scoped`: giới hạn phần lớn tác động của CSS cho component đó.

Khi `temperature.value` thay đổi, Vue tự cập nhật phần giao diện phụ thuộc vào nó. Bạn không cần tự tìm thẻ `<p>` để thay nội dung.

Trong script, truy cập giá trị của `ref` bằng `.value`. Với biến `ref` trực tiếp trong template như ví dụ trên, Vue tự lấy giá trị.

### Một số hàm Vue xuất hiện trong dự án

| Hàm | Cách hiểu | Ví dụ trong dự án |
|---|---|---|
| `ref()` | Dữ liệu Vue theo dõi | Nội dung filter đang nhập, thông báo lỗi |
| `computed()` | Giá trị tính từ dữ liệu khác | Danh sách cột dựa trên `kind` |
| `watch()` | Chạy xử lý khi dữ liệu được theo dõi thay đổi | Tải lại danh sách khi query thay đổi |
| `onMounted()` | Chạy khi component đã được gắn vào giao diện | Tải dữ liệu ban đầu |
| `onUnmounted()` | Chạy khi component bị gỡ khỏi giao diện | Hủy request, timer và listener |

Vue cập nhật giao diện theo dữ liệu đã thay đổi. Việc lấy dữ liệu mới từ backend vẫn do code gọi API hoặc polling thực hiện.

## 3. Vai trò các thư mục

Vue cho phép lựa chọn cách chia thư mục. Các tên bên dưới là cách tổ chức của frontend IoT để mỗi phần có trách nhiệm rõ ràng.

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts
└── src/
    ├── main.ts
    ├── App.vue
    ├── styles.css
    ├── app/
    ├── views/
    ├── components/
    │   ├── common/
    │   ├── dashboard/
    │   └── listing/
    ├── composables/
    ├── api/
    ├── stores/
    ├── types/
    ├── config/
    ├── utils/
    └── assets/
```

| Thư mục | Chứa gì | Ví dụ |
|---|---|---|
| `app/` | Khung ứng dụng và điều hướng | `AppShell.vue`, `router.ts` |
| `views/` | Component đại diện cho một trang | `DashboardView.vue`, `ProfileView.vue` |
| `components/common/` | Phần giao diện dùng ở nhiều trang | Header, badge, phân trang |
| `components/dashboard/` | Phần giao diện của Dashboard | Card cảm biến, biểu đồ, card thiết bị |
| `components/listing/` | Phần giao diện danh sách | Bảng, bộ lọc, trang danh sách dùng chung |
| `composables/` | Logic Vue có thể tái sử dụng | Lọc danh sách, tải dữ liệu, theo dõi lệnh |
| `api/` | Đọc dữ liệu mock hoặc gọi backend | `mock.ts`, `http.ts`, `index.ts` |
| `stores/` | Trạng thái dùng chung qua Pinia | Lệnh điều khiển đang xử lý |
| `types/` | Khai báo cấu trúc dữ liệu bằng TypeScript | `Device`, `CommandResource`, `IoTApi` |
| `config/` | Cấu hình ứng dụng | Nguồn dữ liệu, profile, phân trang |
| `utils/` | Hàm hỗ trợ | Định dạng số, ngày giờ |
| `assets/` | Tài nguyên hình ảnh | Logo và các SVG |

Các công cụ đi cùng Vue trong dự án:

- **Vite**: chạy server phát triển và build ứng dụng. Công cụ xử lý file `.vue`, TypeScript và import CSS để trình duyệt sử dụng được.
- **TypeScript**: giúp mô tả kiểu dữ liệu và phát hiện lỗi khi kiểm tra code.
- **Vue Router**: chọn trang theo URL.
- **Pinia**: quản lý trạng thái dùng chung.

## 4. Cách Data và History tái sử dụng giao diện

Trong [SensorDataView.vue](./src/views/SensorDataView.vue), trang Data hiển thị:

```vue
<ListingPage kind="data" />
```

Trong [DeviceHistoryView.vue](./src/views/DeviceHistoryView.vue), trang History hiển thị:

```vue
<ListingPage kind="history" />
```

Cả hai sử dụng [ListingPage.vue](./src/components/listing/ListingPage.vue). `kind` cho component biết đang dựng trang nào.

```text
ListingPage
├── PageHeader        Tiêu đề trang
├── QueryFilters      Bộ lọc
├── ResourceNotice    Thông báo tải dữ liệu hoặc lỗi
├── DataTable         Khung bảng
└── AppPagination     Phân trang
```

Với `kind="data"`, component sử dụng dữ liệu cảm biến và các cột ID, Name, Type, Value, Date & Time.

Với `kind="history"`, component sử dụng lịch sử thiết bị và các cột ID, Device, User, Action, Status, Date & Time.

Nhờ vậy, chỉnh phần phân trang trong `AppPagination.vue` sẽ được áp dụng cho cả hai trang. Component dùng chung nhận dữ liệu và cấu hình khác nhau để hiển thị đúng từng trường hợp.

## 5. Component trao đổi dữ liệu như thế nào

Hai hướng trao đổi cơ bản là:

```text
Component cha ── props ──→ Component con
Component cha ←─ event ── Component con
```

### Props: cha đưa dữ liệu xuống con

Ví dụ:

```vue
<DataTable :rows="data?.results || []" :columns="columns" />
```

`ListingPage` đưa danh sách bản ghi và cấu hình cột cho `DataTable`. Bảng dùng dữ liệu đó để dựng hàng và cột.

Dấu `:` cho biết giá trị bên phải là biểu thức hoặc biến trong script. Ví dụ `:columns="columns"` truyền giá trị của biến `columns`.

### Event: con thông báo thao tác lên cha

Ví dụ thực tế trong `ListingPage`:

```vue
<QueryFilters
  v-model="draft"
  :kind="kind"
  :devices="devices"
  @apply="apply"
  @reset="reset"
/>
```

- `kind` và `devices` được truyền xuống bộ lọc.
- `v-model="draft"` liên kết dữ liệu các ô nhập với bộ lọc đang nhập.
- Khi người dùng bấm Filter, `QueryFilters` phát event `apply`.
- Component cha nhận event và gọi hàm `apply()`.
- Bấm Reset cũng đi theo luồng tương tự.

### Slot: cha cung cấp cách hiển thị bên trong con

`DataTable` nhận cấu hình cột và dựng khung bảng. `ListingPage` cung cấp cách hiển thị từng ô qua slot:

```vue
<DataTable :rows="rows" :columns="columns">
  <template #cell="{ row, column }">
    <!-- Nội dung ô tùy theo row và column -->
  </template>
</DataTable>
```

Ví dụ ô User gồm SVG và username; ô Status dùng `StatusBadge`. Cách hiển thị này được cung cấp từ cha, giúp cùng một `DataTable` phục vụ được cả Data và History.

## 6. Luồng xử lý khi bấm Filter

```text
Người dùng bấm Filter
    ↓
QueryFilters phát event apply
    ↓
ListingPage gọi apply() trong useListing
    ↓
useListing cập nhật điều kiện lọc trên URL
    ↓
useLiveResource gọi hàm lấy dữ liệu
    ↓
api.sensorData() hoặc api.history()
    ↓
Dữ liệu trả về được gán vào state
    ↓
Vue cập nhật DataTable
```

### `useListing`: logic danh sách

[useListing.ts](./src/composables/useListing.ts) quản lý:

- `draft`: bộ lọc người dùng đang nhập.
- `applied`: bộ lọc đã áp dụng, lấy từ query của URL.
- Trang hiện tại và số bản ghi mỗi trang.
- Sắp xếp.
- Các hàm Filter, Reset và đổi trang.

Tách `draft` và `applied` giúp người dùng nhập điều kiện trước, rồi bấm Filter để áp dụng.

### `useLiveResource`: logic tải dữ liệu

[useLiveResource.ts](./src/composables/useLiveResource.ts) quản lý:

- `data`: kết quả đã lấy được.
- `loading`: có đang tải hay không.
- `error`: thông báo lỗi.
- `refresh()`: tải lại dữ liệu.
- Polling trong chế độ API và việc dọn dẹp khi rời trang.

Các hàm tái sử dụng logic có trạng thái như vậy được gọi là **composable**. Tên thường bắt đầu bằng `use`.

### `api/`: nơi chọn nguồn dữ liệu

[api/index.ts](./src/api/index.ts) chọn adapter theo cấu hình:

```text
VITE_DATA_SOURCE=mock → mock.ts → Dữ liệu giả
VITE_DATA_SOURCE=api  → http.ts → Request tới backend
```

Các trang gọi cùng những hàm như `api.sensorData()` và `api.history()`. Cả hai adapter thực hiện cùng interface `IoTApi`, nên giao diện và bộ lọc sử dụng cùng cách gọi khi đổi nguồn dữ liệu.

Backend thật cần trả đúng cấu trúc dữ liệu mà adapter và TypeScript đã khai báo. Chi tiết chạy và cấu hình được trình bày trong [README](./README.md).

## 7. Pinia và trạng thái dùng chung

Trong dự án, [stores/deviceControl.ts](./src/stores/deviceControl.ts) giữ thông tin lệnh bật/tắt đang xử lý:

- Thiết bị nào đang có lệnh.
- Action đã yêu cầu.
- Command ID và idempotency key.
- Lệnh đang chờ hay đang đối chiếu kết quả.

Ví dụ: bạn bật đèn rồi chuyển sang History. Khi quay lại Dashboard, ứng dụng còn thông tin lệnh để tiếp tục kiểm tra kết quả.

Store này cũng lưu metadata vào `sessionStorage`. Pinia giữ trạng thái dùng chung khi ứng dụng đang chạy; `sessionStorage` hỗ trợ khôi phục metadata sau khi reload trong cùng phiên tab.

Bạn có thể phân biệt các phần bằng công việc của chúng:

| Phần | Công việc chính |
|---|---|
| Component | Hiển thị giao diện và nhận thao tác |
| Composable | Thực hiện logic Vue có thể tái sử dụng |
| Store | Giữ trạng thái dùng chung |
| API adapter | Trao đổi với nguồn dữ liệu |
| Utility | Thực hiện tác vụ hỗ trợ như định dạng |

## 8. Nên mở file nào khi cần sửa

| Muốn sửa gì | File nên xem đầu tiên |
|---|---|
| Sidebar, logo, điều hướng | [AppShell.vue](./src/app/AppShell.vue) |
| Thêm hoặc đổi URL một trang | [router.ts](./src/app/router.ts) |
| Bố cục Dashboard | [DashboardView.vue](./src/views/DashboardView.vue) |
| Card cảm biến | [SensorCard.vue](./src/components/dashboard/SensorCard.vue) |
| Biểu đồ | [SensorTrendsChart.vue](./src/components/dashboard/SensorTrendsChart.vue) |
| Các cột, icon và nội dung ô ở Data/History | [ListingPage.vue](./src/components/listing/ListingPage.vue) |
| Các ô nhập bộ lọc | [QueryFilters.vue](./src/components/listing/QueryFilters.vue) |
| Cách bảng dựng hàng và cột | [DataTable.vue](./src/components/listing/DataTable.vue) |
| Giao diện phân trang | [AppPagination.vue](./src/components/common/AppPagination.vue) |
| Logic Filter, Reset, sắp xếp, đổi trang | [useListing.ts](./src/composables/useListing.ts) |
| Dữ liệu giả | [mock.ts](./src/api/mock.ts) |
| URL endpoint và request HTTP | [http.ts](./src/api/http.ts) |
| Thông tin cá nhân và project link | [profile.ts](./src/config/profile.ts) |
| Font, màu và CSS chung | [styles.css](./src/styles.css) |

Để bắt đầu đọc code, hãy đi theo thứ tự:

```text
main.ts
→ App.vue
→ AppShell.vue
→ router.ts
→ một file trong views/
→ các component mà trang đó sử dụng
→ composables/
→ api/
```

Bạn có thể bắt đầu với trang Data vì view của nó rất ngắn, sau đó đi vào `ListingPage` để thấy cách các phần giao diện được ghép lại.

## Tài liệu chính thức để đọc thêm

- [Cấu trúc file Vue](https://vuejs.org/api/sfc-spec)
- [Component, props và event](https://vuejs.org/guide/essentials/component-basics.html)
- [Reactive state và ref](https://vuejs.org/guide/essentials/reactivity-fundamentals)
- [Composable](https://vuejs.org/guide/reusability/composables)
- [Vue Router](https://router.vuejs.org/guide/)

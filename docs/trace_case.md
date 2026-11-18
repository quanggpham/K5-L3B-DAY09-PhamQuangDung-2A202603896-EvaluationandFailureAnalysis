# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case của tôi: `swarm C-002@55`

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55` (item E-002), run ID `E-swarm-<ngày chạy>-<4 ký tự sha eval set>` trong `reports/baseline_v1.json`; trial fail duy nhất của baseline (69/70 pass) |
| Triệu chứng | Grader Lab 8 FAIL: `status resolved != denied`. Ledger ghi 20.000đ (1 dòng), nhãn là 0đ (`denied`). `pass_rate`, `refund_amount_correct` và `db_fact_kept` cùng fail. Trace của `swarm` không có event `reply`, nên phải đọc ledger, không đọc reply |
| Bước sai đầu tiên | Event 3 `model_override {"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng (scope `owner_order_only`). Event 2 `investigator` đọc đơn O-202 từ DB với `delay_days=2`, chưa đủ ngưỡng để được bồi thường. Event 3 ghi đè 2 bằng 5 (số khách viết trong ticket). Event 4 `quote` 20.000đ (SHIP-LATE-03) chỉ là hệ quả của số ngày bị đè; host rồi ghi đúng 20.000đ vào ledger |
| Failure mode | FM-03 `ticket_trust` (tin ticket hơn DB), xem `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@55`: event 3 là `quote` với `amount_vnd: 0`, `reason: no_entitlement` (không có `model_override`), reply "chưa đủ điều kiện hoàn", ledger 0, grader Lab 8 PASS |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_c002_fails_when_ticket_beats_db` chạy `seeded_regression` (cùng lỗi `ticket_trust`, lỗi ở cả 5 seed của C-002) và assert `TrialPass`, `DbFactKept`, `RefundAmountCorrect` đều False cùng event `model_override {"delay_days": 5}`; `test_lab9_trace_case_c002_passes_when_db_is_kept` chạy `fixed` và assert cả ba đều True. Đã chạy: fail trên variant lỗi, pass trên `fixed`. Cùng lỗi này làm `pass_rate` của `seeded_regression` giảm và bị gate chặn |
| Chưa chắc chắn | Test dùng `seeded_regression` chứ không phải `swarm` thật, vì `swarm` là code Lab 8 (không sửa) và chỉ lỗi ở seed chia hết cho 5. Trace `swarm` không có event `reply` nên không kiểm được lời báo cho khách. Chưa rõ vì sao `swarm_reference` gắn điểm yếu vào `seed % 5 == 0` (suy từ `variant_agent`, bản sao của swarm, không đọc được nguồn trong lab này) |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

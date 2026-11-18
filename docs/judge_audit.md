# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (judge replay, FAIL là lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (exit 0) | **dùng**, chỉ làm metric báo cáo/không blocking cho tiền |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt**: κ và R dưới sàn (exit 1) | **loại**, không được làm gate |

Ma trận nhầm lẫn (FAIL = dương):

| Tiêu chí | tp | fp | fn | tn | Tỉ lệ FAIL quan sát → hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 → 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 → 0.30 |

## ≥5 case audit thủ công

Lấy toàn bộ 10 bất đồng của `tone_ok` và 5 case đại diện của `helpful` (21 bất đồng của `helpful` đều cùng chiều: người FAIL, judge PASS).

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại; judge hiểu thân mật là lịch sự. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn…" | PASS | FAIL | Người | Gọi khách là "bạn"; cùng lỗi với #1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh; judge bám vào từ khóa "Dạ, vui lòng". |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ…" | FAIL | PASS | Người | Ngắn mà đủ ý; judge phạt vì thiếu câu xin lỗi, rubric không bắt buộc xin lỗi. |
| 5 | H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CS LogiX cho phép "refund"; judge phạt mọi từ tiếng Anh. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa hoàn thêm ngoài kết quả hệ thống. Đây là lỗi nội dung (cam kết sai), không phải giọng điệu; nên chuyển sang check code. |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Ghi chú của bộ dữ liệu: nhãn người sai do đọc nhầm ticket. Sửa nhãn người thành FAIL. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | Không rõ | Lặp "Dạ" do lỗi gõ; lỗi nhỏ, rubric chưa nói lỗi gõ có tính là FAIL không. Cần thêm quy tắc vào rubric. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy); judge không phạt. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge không thấy ledger nên không thể biết số tiền sai (FM-08). |
| 12 | HL-016 xin lỗi 2 lần + "đã hoàn 55.000đ cho đơn O-404" | PASS | FAIL | Người | Ledger ghi 35.000đ; câu trả lời dài, nhiều lời xin lỗi được judge chấm "hữu ích" (thiên vị độ dài/độ lễ phép). |
| 13 | HL-043 xin lỗi lặp lại + "đã hoàn 35.000đ cho đơn O-202" | PASS | FAIL | Người | Ledger ghi 20.000đ; cùng mẫu với #12. |
| 14 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả, không nói số tiền: không giúp được khách. |
| 15 | HL-087 "Dạ, LogiX đã hoàn 60.000đ cho đơn O-202 ạ." | PASS | FAIL | Người | Ledger ghi 90.000đ; reply báo thiếu tiền. |

Phân loại 21 FN của `helpful`: 18 case số tiền trong reply khác ledger (13 trong số đó là reply dài, xin lỗi lặp lại; 5 là reply ngắn), 3 case "Ok bạn, đơn … xử lý rồi nhé" không có thông tin.

## Sửa rubric

- **tone_ok:** (a) xưng hô bắt buộc "anh/chị", xưng "LogiX"; "em/bạn/nha/nhé" là FAIL (#1, #2). (b) Câu mệnh lệnh với khách là FAIL dù có "Dạ" (#3). (c) Xin lỗi là tùy chọn, không thiếu thì không FAIL (#4). (d) Thêm whitelist thuật ngữ được phép như "refund" (#5). (e) Emoji và mất dấu tiếng Việt là FAIL (#7, #10). (f) Lỗi gõ lặp từ: ghi rõ là PASS nếu không đổi nghĩa (#9). (g) Hứa hẹn ngoài kết quả hệ thống (#6) tách khỏi tone, chuyển sang check code.
- **helpful:** bỏ khỏi judge phần "số tiền đúng", chấm bằng code (so số tiền trong reply với `refund_vnd` của ledger, chính là metric FM-08 ở M3). Phần còn lại của judge chỉ chấm "reply có nêu kết quả + bước tiếp theo", kèm ví dụ few-shot reply dài nhưng sai là FAIL để giảm thiên vị độ dài. Phải calibrate lại trên nhãn mới trước khi dùng.

## Kết luận

- **Loại `helpful` khỏi gate.** Recall 0.30 nghĩa là judge bỏ sót 21/30 reply thật sự không hữu ích; κ 0.375 dưới sàn 0.6. Precision 1.0 không cứu được: một judge gần như luôn nói PASS có precision cao nhưng gate sẽ cho qua hầu hết regression. Rogan-Gladen kéo tỉ lệ lỗi 0.09 về 0.30 (khớp tỉ lệ thật 30/100), nhưng với sensitivity 0.3 phép hiệu chỉnh khuếch đại nhiễu gấp khoảng 3 lần (chia cho sens + spec − 1 = 0.3), nên không dùng để chặn PR từng điểm phần trăm. Nguyên nhân gốc: judge không có ledger nên không thể chấm số tiền, mà 18/21 case bỏ sót là số tiền sai. Tiền phải chấm bằng code.
- **Giữ `tone_ok`** (đạt cả ba sàn), nhưng 8/10 bất đồng là lỗi của judge (1 lỗi nhãn người, 1 chưa rõ), nên chỉ dùng làm metric phụ, không blocking, cho tới khi áp dụng rubric sửa ở trên và calibrate lại.
- **Sửa nhãn:** H-081 nhãn người sai, đổi thành FAIL. Sau khi sửa, `tone_ok` có tp 25, fp 3, fn 6, tn 66.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai, và rubric đang được sửa dựa chính trên các case này. Cần nhãn người mới, held-out thật, để đo lại; κ và P/R ở đây có thể lạc quan.

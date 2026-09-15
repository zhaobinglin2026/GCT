import csv
import os
import re
import sys
from datetime import datetime


def parse_filename_date(filename):
    first = filename.find('_')
    if first == -1:
        raise ValueError(f"文件名 {filename} 中没有下划线，无法解析日期")

    second = filename.find('_', first + 1)
    if second == -1:
        raise ValueError(f"文件名 {filename} 中没有第二个下划线，无法解析日期")

    rest = filename[second + 1:]
    if len(rest) < 6 or not rest[:6].isdigit():
        raise ValueError(f"文件名 {filename} 第二个下划线后不是连续 6 位数字，无法解析日期")

    date_str = rest[:6]
    yy = int(date_str[0:2])
    mm = int(date_str[2:4])
    dd = int(date_str[4:6])
    year = 2000 + yy
    return datetime(year, mm, dd)


def parse_time_of_day(time_str):
    time_str = time_str.strip()
    if not re.fullmatch(r'\d{2}:\d{2}:\d{2}\.\d{3}', time_str):
        raise ValueError(f"Time of Day 格式不正确：{time_str}")

    try:
        t = datetime.strptime(time_str, "%H:%M:%S.%f")
    except ValueError as e:
        raise ValueError(f"Time of Day 解析失败：{time_str}") from e

    return t.time()


def get_file_sort_datetime(filepath, filename, header):
    with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # 跳过表头

        first_data = None
        for row in reader:
            if any(cell != '' for cell in row):
                first_data = row
                break

        if first_data is None:
            raise ValueError(f"文件 {filename} 没有非空数据行")

    time_col = "Time of Day[HH:mm:ss.ms]"
    idx = header.index(time_col)

    if idx >= len(first_data):
        raise ValueError(f"文件 {filename} 第一行非空数据缺少 {time_col} 列的值")

    time_str = first_data[idx].strip()
    time_part = parse_time_of_day(time_str)

    date_part = parse_filename_date(filename)
    return datetime.combine(date_part.date(), time_part)


def main():
    folder = input("请输入目标文件夹路径：").strip()

    if not folder:
        raise ValueError("文件夹路径不能为空")

    if not os.path.isdir(folder):
        raise ValueError(f"文件夹不存在或不是文件夹：{folder}")

    output_file = os.path.join(folder, "merged.csv")
    all_names = os.listdir(folder)

    candidates = []
    for name in all_names:
        if name == "merged.csv":
            continue
        if name.startswith("raw") and name.endswith(".csv"):
            candidates.append(name)

    if not candidates:
        raise ValueError("没有找到候选文件（以 raw 开头、以 .csv 结尾）")

    base_name = candidates[0]
    base_path = os.path.join(folder, base_name)

    with open(base_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        base_header = next(reader, None)

    if base_header is None:
        raise ValueError(f"基准文件 {base_name} 为空，没有表头")

    time_col = "Time of Day[HH:mm:ss.ms]"
    if time_col not in base_header:
        raise ValueError(f"基准文件 {base_name} 缺少列：{time_col}")

    valid_files = []

    try:
        sort_dt = get_file_sort_datetime(base_path, base_name, base_header)
    except Exception as e:
        raise ValueError(f"基准文件 {base_name} 解析失败：{e}") from e

    valid_files.append((base_name, base_path, sort_dt))

    for name in candidates[1:]:
        path = os.path.join(folder, name)

        try:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
        except Exception as e:
            print(f"跳过文件：{name}，原因：读取失败：{e}")
            continue

        if header is None:
            print(f"跳过文件：{name}，原因：空文件或没有表头")
            continue

        if header != base_header:
            if time_col not in header:
                print(f"跳过文件：{name}，原因：缺少列 {time_col}")
            else:
                print(f"跳过文件：{name}，原因：表头与基准文件不一致")
            continue

        try:
            sort_dt = get_file_sort_datetime(path, name, base_header)
        except Exception as e:
            raise ValueError(f"文件 {name} 解析失败：{e}") from e

        valid_files.append((name, path, sort_dt))

    if len(valid_files) < 2:
        raise ValueError(f"有效文件少于 2 个（当前 {len(valid_files)} 个），终止，不生成 merged.csv")

    seen = {}
    for name, path, sort_dt in valid_files:
        if sort_dt in seen:
            raise ValueError(f"两个文件的最早时间相同：{seen[sort_dt]} 和 {name}，时间：{sort_dt}")
        seen[sort_dt] = name

    valid_files.sort(key=lambda x: x[2])

    with open(output_file, 'w', encoding='utf-8-sig', newline='') as out_f:
        writer = csv.writer(out_f)
        writer.writerow(base_header)

        for name, path, sort_dt in valid_files:
            with open(path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                next(reader, None)  # 跳过表头
                for row in reader:
                    writer.writerow(row)

            print(f"已合并文件：{name}（时间：{sort_dt}）")

    print(f"合并完成，输出文件：{output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)
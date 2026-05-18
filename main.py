"""
External Merge Sort – Full Pipeline
=====================================
A single, production-ready script that combines:
  - Constants & Dataclass
  - Data Generation
  - Phase 1: In-Memory Sorting (Chunking)
  - Phase 2: Multi-way External Merge (Min-Heap)
  - Driver Code
"""

import contextlib
import csv
import heapq
import os
import random
import time
from dataclasses import dataclass, fields


# ---------------------------------------------------------------------------
# Constants & Dataclass
# ---------------------------------------------------------------------------

_OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Added folders for better organization
DATA_DIR = os.path.join(_OUTPUT_DIR, "data")
SORTED_DIR = os.path.join(_OUTPUT_DIR, "sorted_chunks")
FINAL_OUTPUT_DIR = os.path.join(_OUTPUT_DIR, "output")

# Create folders automatically if they do not exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SORTED_DIR, exist_ok=True)
os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

_NUM_FILES = 16
_RECORDS_PER_FILE = 1_000
_FIELDNAMES = ["employee_id", "last_name", "first_name", "department", "salary"]

_FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael",
    "Linda", "William", "Barbara", "David", "Elizabeth", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Emma",
    "Olivia", "Noah", "Liam", "Ava", "Sophia", "Isabella", "Mia", "Lucas",
    "Mason", "Ethan", "Aiden", "Harper", "Evelyn", "Amelia", "Charlotte",
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
]

_DEPARTMENTS = [
    "Engineering", "Marketing", "Sales", "Human Resources", "Finance",
    "Operations", "Legal", "Research & Development", "Customer Support",
    "Product Management", "IT", "Logistics",
]

_SALARY_MIN = 30_000.0
_SALARY_MAX = 150_000.0


@dataclass
class Employee:
    """Represents a single employee record."""
    employee_id: int
    last_name: str
    first_name: str
    department: str
    salary: float


# ---------------------------------------------------------------------------
# Data Generation
# ---------------------------------------------------------------------------

def _random_employee(employee_id: int) -> Employee:
    """Create a single Employee instance with randomized field values."""
    return Employee(
        employee_id=employee_id,
        last_name=random.choice(_LAST_NAMES),
        first_name=random.choice(_FIRST_NAMES),
        department=random.choice(_DEPARTMENTS),
        salary=round(random.uniform(_SALARY_MIN, _SALARY_MAX), 2),
    )


def generate_dummy_data() -> None:
    """
    Generate 16 CSV files (data_1.csv … data_16.csv) in the same directory
    as this script.  Each file contains exactly 1,000 employee records with
    completely randomized field values.  employee_id values are shuffled so
    they are NOT in sorted order within any file.
    """
    total_records = _NUM_FILES * _RECORDS_PER_FILE
    all_ids = list(range(1, total_records + 1))
    random.shuffle(all_ids)  # Ensure IDs are NOT sorted

    header = [f.name for f in fields(Employee)]

    for file_index in range(1, _NUM_FILES + 1):
        file_name = f"data_{file_index}.csv"
        file_path = os.path.join(DATA_DIR, file_name)

        start = (file_index - 1) * _RECORDS_PER_FILE
        end = start + _RECORDS_PER_FILE
        file_ids = all_ids[start:end]

        with open(file_path, mode="w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(header)
            for emp_id in file_ids:
                emp = _random_employee(emp_id)
                writer.writerow([
                    emp.employee_id,
                    emp.last_name,
                    emp.first_name,
                    emp.department,
                    emp.salary,
                ])

        print(f"Created {file_name} with {_RECORDS_PER_FILE} records.")

    print(f"\nDone. {_NUM_FILES} CSV files written to: {DATA_DIR}")


# ---------------------------------------------------------------------------
# Phase 1 (Sorting)
# ---------------------------------------------------------------------------

def phase_1_sort_chunks() -> None:
    """
    For each data_i.csv (i = 1 … 16):
      1. Read all 1,000 records into a list.
      2. Sort the list by employee_id in ascending numerical order.
      3. Write the sorted records to sorted_chunk_i.csv.
      4. Clear the list to free memory before moving to the next file.
    """
    for i in range(1, _NUM_FILES + 1):
        input_path = os.path.join(DATA_DIR, f"data_{i}.csv")
        output_path = os.path.join(SORTED_DIR, f"sorted_chunk_{i}.csv")

        # --- Read all records into memory ---
        records = []
        with open(input_path, mode="r", newline="", encoding="utf-8") as in_file:
            reader = csv.DictReader(in_file)
            for row in reader:
                records.append(row)

        # --- Sort in-memory by employee_id (integer comparison) ---
        records.sort(key=lambda row: int(row["employee_id"]))

        # --- Write the sorted records to the chunk file ---
        with open(output_path, mode="w", newline="", encoding="utf-8") as out_file:
            writer = csv.DictWriter(out_file, fieldnames=_FIELDNAMES)
            writer.writeheader()
            writer.writerows(records)

        print(f"Sorted and wrote sorted_chunk_{i}.csv  ({len(records)} records)")

        # --- Clear the list to free memory ---
        records.clear()

    print(f"\nPhase 1 complete. {_NUM_FILES} sorted chunk files written to: {SORTED_DIR}")


# ---------------------------------------------------------------------------
# Phase 2 (Merging)
# ---------------------------------------------------------------------------

def phase_2_multi_way_merge() -> None:
    """
    Merge all 16 sorted chunk files into final_sorted_employees.csv.

    Algorithm:
      1. Open every sorted_chunk_i.csv for reading.
      2. Skip (consume) each file's header row.
      3. Seed the Min-Heap with the first data row from each file as:
             (employee_id_int, file_index, row_dict)
      4. Repeatedly pop the smallest element, write it to the output file,
         and immediately refill the heap from the same source file.
      5. Close all input files when the heap is exhausted.
    """
    output_path = os.path.join(FINAL_OUTPUT_DIR, "final_sorted_employees.csv")

    # Open all 16 input files via ExitStack so every handle is closed
    # automatically – even if one file fails to open mid-loop.
    with contextlib.ExitStack() as stack:
        readers = []
        for i in range(1, _NUM_FILES + 1):
            chunk_path = os.path.join(SORTED_DIR, f"sorted_chunk_{i}.csv")
            fh = stack.enter_context(
                open(chunk_path, mode="r", newline="", encoding="utf-8")
            )
            readers.append(csv.DictReader(fh))

        out_file = stack.enter_context(
            open(output_path, mode="w", newline="", encoding="utf-8")
        )
        writer = csv.DictWriter(out_file, fieldnames=_FIELDNAMES)
        writer.writeheader()

        def _parse_id(row: dict, source: str) -> int:
            """Cast employee_id to int; raise a descriptive error on bad data."""
            raw = row.get("employee_id", "")
            try:
                return int(raw)
            except ValueError:
                raise ValueError(
                    f"Non-integer employee_id {raw!r} found in {source}"
                ) from None

        # Seed the heap with the first row from each file.
        # Tuple: (employee_id, file_index, row_dict)
        # file_index is included as a tiebreaker to avoid comparing dicts.
        heap: list = []
        for file_index, reader in enumerate(readers):
            row = next(reader, None)
            if row is not None:
                eid = _parse_id(row, f"sorted_chunk_{file_index + 1}.csv")
                heapq.heappush(heap, (eid, file_index, row))

        # --- Main merge loop ---
        total_written = 0
        while heap:
            _, file_index, row_dict = heapq.heappop(heap)
            writer.writerow(row_dict)
            total_written += 1

            next_row = next(readers[file_index], None)
            if next_row is not None:
                eid = _parse_id(
                    next_row, f"sorted_chunk_{file_index + 1}.csv"
                )
                heapq.heappush(heap, (eid, file_index, next_row))

    print(
        f"Phase 2 complete. {total_written} records written to: {output_path}"
    )


# ---------------------------------------------------------------------------
# Driver Code
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("   External Merge Sort – Full Pipeline")
    print("=" * 60)

    total_start = time.time()

    # ── Data Generation ──────────────────────────────────────────────────────
    print("\n[1/3] Data Generation")
    print("-" * 40)
    t0 = time.time()
    generate_dummy_data()
    t1 = time.time()
    data_gen_time = t1 - t0
    print(f"\n  ✓ Data Generation time : {data_gen_time:.4f} seconds")

    # ── Phase 1: In-Memory Sorting (Chunking) ─────────────────────────────
    print("\n[2/3] Phase 1 – Sorting Chunks")
    print("-" * 40)
    t0 = time.time()
    phase_1_sort_chunks()
    t1 = time.time()
    phase1_time = t1 - t0
    print(f"\n  ✓ Phase 1 (Sorting) time: {phase1_time:.4f} seconds")

    # ── Phase 2: Multi-way External Merge ─────────────────────────────────
    print("\n[3/3] Phase 2 – Multi-way External Merge")
    print("-" * 40)
    t0 = time.time()
    phase_2_multi_way_merge()
    t1 = time.time()
    phase2_time = t1 - t0
    print(f"\n  ✓ Phase 2 (Merging) time: {phase2_time:.4f} seconds")

    # ── Summary ──────────────────────────────────────────────────────────────
    total_time = time.time() - total_start

    print("\n" + "=" * 60)
    print("   Execution Time Summary")
    print("=" * 60)
    print(f"  Data Generation : {data_gen_time:>10.4f} seconds")
    print(f"  Phase 1 (Sort)  : {phase1_time:>10.4f} seconds")
    print(f"  Phase 2 (Merge) : {phase2_time:>10.4f} seconds")
    print(f"  {'─' * 36}")
    print(f"  Total           : {total_time:>10.4f} seconds")
    print("=" * 60)


# ===========================================================================
# COMPLEXITY SUMMARY
# Time Complexity: O(N log N) - Achieved via Phase 1 Chunking and Phase 2 Min-Heap.
# Space Complexity: O(M) - Bounded by chunk size, strictly respecting memory limits.
# * For detailed mathematical analysis, please refer to the attached Project Report.
# ===========================================================================
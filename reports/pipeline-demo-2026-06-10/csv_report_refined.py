"""
This module provides functionality to read a CSV file containing spending data,
calculate totals per category, and generate a summary report.
"""
import sys
from typing import List, Dict, Optional


def load_rows(path: str) -> List[List[str]]:
    """
    Read a CSV file and return its contents as a list of rows.

    Args:
        path (str): The file path to the CSV file to be read.

    Returns:
        List[List[str]]: A list where each element is a list of strings representing 
        the columns of a single row in the CSV.
    """
    rows = []
    with open(path) as f:
        for line in f:
            # Remove whitespace and split the line by commas to create a list of values
            rows.append(line.strip().split(','))
    return rows


def category_totals(rows: List[List[str]]) -> Dict[str, float]:
    """
    Calculate the total spending amount for each category.

    Args:
        rows (List[List[str]]): A list of rows, where each row is a list of strings.
        Assumes row[0] is the category name and row[2] is the spending amount.

    Returns:
        Dict[str, float]: A dictionary where keys are category names and values 
        are the sum of amounts for that category.
    """
    totals: Dict[str, float] = {}
    
    # Skip the header row (index 0) and iterate through the data rows
    for row in rows[1:]:
        category = row[0]
        amount = float(row[2])
        
        # Add the amount to the existing category total or initialize it
        if category in totals:
            totals[category] += amount
        else:
            totals[category] = amount
            
    return totals


def top_category(totals: Dict[str, float]) -> Optional[str]:
    """
    Find the category with the highest total spending.

    Args:
        totals (Dict[str, float]): A dictionary mapping category names to total amounts.

    Returns:
        Optional[str]: The name of the category with the highest total, or None if 
        the input dictionary is empty.
    """
    best = None
    # Compare each category's total to find the maximum value
    for name, amount in totals.items():
        if best is None or amount > totals[best]:
            best = name
    return best


def make_report(path: str) -> str:
    """
    Generate a formatted spending report string from a CSV file.

    Args:
        path (str): The file path to the CSV data.

    Returns:
        str: A multi-line string containing the report header, category totals, 
        and the top category.
    """
    # Load raw data and aggregate totals by category
    rows = load_rows(path)
    totals = category_totals(rows)
    
    # Initialize the report with a title and separator
    lines = ["Spending report", "==============="]
    
    # Sort categories alphabetically and append each to the report lines
    for name in sorted(totals):
        lines.append(name + ": " + str(round(totals[name], 2)))
        
    # Identify and append the category with the highest spending
    lines.append("Top category: " + str(top_category(totals)))
    
    # Combine all lines into a single string separated by newline characters
    return "\n".join(lines)


if __name__ == "__main__":
    # Read the file path from command line arguments and print the generated report
    if len(sys.argv) > 1:
        print(make_report(sys.argv[1]))

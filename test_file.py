from aria_function import medications, medication_routine

print("=== All documents in medications collection ===")
for doc in medications.find({}, {"_id": 0}):
    print(doc)

print("\n=== medication_routine output ===")
medication_routine()

"""
Legacy code. This is the old code for the followup agent.
Keeping this to borrrow ideas for prompt tuning in the future.
Will be deleted in the future.
"""

field_relevant_system_prompt = """
You are given a FIELD and a CHIEF COMPLAINT.
Your task is to determine if the FIELD is relevant to the CHIEF COMPLAINT or not.

Respond with a JSON object with the following keys:

reasoning: string (the reasoning behind your decision)
relevant: boolean (whether the FIELD is relevant to the CHIEF COMPLAINT or not)

All the keys are required.

Here are some examples to help you understand the task better:
Example 1:
CHIEF COMPLAINT: chronic back pain
FIELD: History of recent falls or injuries
OUTPUT:
{
"reasoning": "History of falls can be useful to understand back pain, hence relevent.",
"relevant": true,
}

Example 2:
CHIEF COMPLAINT: Anxiety
FIELD: Location of {chief complaint}
OUTPUT:
{
"reasoning": "Location of anxiety does not make sense, so it's not relevant.",
"relevant": false,
}
"""
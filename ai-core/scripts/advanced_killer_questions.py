"""
Advanced Killer Questions - Stress Test the Bot

These questions are designed to be extremely challenging and test edge cases
that could break the bot or cause confusion.
"""

ADVANCED_KILLER_QUESTIONS = {
    "SUBJECT_CONFUSION": {
        "description": "Ambiguous subject names that could match multiple subjects",
        "questions": [
            "I need help with English",  # Could be ENG, ESL, or English as a subject
            "Who is the science librarian?",  # Too broad - biology, chemistry, physics?
            "Business help",  # Business, Business Analytics, Business Law?
            "I'm studying art",  # Art, Art History, Art Education?
            "Math librarian",  # Mathematics, Applied Math, Statistics?
            "Who helps with communication?",  # Communications, Speech Communication, Mass Communication?
            "Engineering research help",  # Multiple engineering disciplines
            "Education librarian contact",  # Education, Educational Leadership, Special Education?
        ]
    },
    
    "TYPOS_AND_MISSPELLINGS": {
        "description": "Common typos in subject and course names",
        "questions": [
            "Who is the psycology librarian?",  # Psychology
            "I need help with biologee",  # Biology
            "ENG 11 librarian",  # Missing digit - ENG 111?
            "Chemestry research guide",  # Chemistry
            "Histroy subject librarian",  # History
            "Mathmatics help",  # Mathematics
            "Buisness librarian email",  # Business
            "Phsyics research resources",  # Physics
            "Sociolgy course guide",  # Sociology
            "Politcal science librarian",  # Political
        ]
    },
    
    "COURSE_CODE_VARIATIONS": {
        "description": "Different ways students write course codes",
        "questions": [
            "ENG111",  # No space
            "ENG 111",  # With space
            "eng 111",  # Lowercase
            "Eng 111",  # Mixed case
            "ENG-111",  # With dash
            "ENG.111",  # With period
            "English 111",  # Full name with number
            "ENG one eleven",  # Written out
            "ENG 1 1 1",  # Extra spaces
        ]
    },
    
    "MULTI_SUBJECT_CONFUSION": {
        "description": "Questions mentioning multiple subjects",
        "questions": [
            "I need help with both biology and chemistry",
            "Who is the librarian for English and History?",
            "I'm double majoring in Psychology and Sociology, who can help?",
            "Business and Economics research help",
            "I'm taking ENG 111 and PSY 201, who is my librarian?",
            "Art and Music librarian contact",
            "I need guides for both Math and Physics",
        ]
    },
    
    "VAGUE_REQUESTS": {
        "description": "Extremely vague questions that need clarification",
        "questions": [
            "I need help",
            "Research",
            "Librarian",
            "Guide",
            "Resources",
            "Help me",
            "I have a question",
            "Library stuff",
            "Need info",
        ]
    },
    
    "COMPLEX_NESTED_QUESTIONS": {
        "description": "Questions with multiple nested parts",
        "questions": [
            "If I'm taking ENG 111 but also need help with my Biology research paper about genetics, and I want to book a study room for tomorrow at 2pm, and also what time does the library close on Friday, who should I talk to?",
            "I'm a Hamilton campus student taking online classes through Oxford campus, need to find articles about psychology for my research paper due next week, but also want to know if I can return books to any campus library, and do you have study rooms available?",
            "My professor said I need peer-reviewed sources from the last 5 years about climate change impacts on agriculture in developing countries, but I don't know how to search databases, and also I need to cite them in APA format, and can I get help with that?",
        ]
    },
    
    "REGIONAL_CAMPUS_CONFUSION": {
        "description": "Questions mixing campuses or unclear campus",
        "questions": [
            "I'm at Hamilton but taking Oxford classes, who is my librarian?",
            "Can I use the King Library if I'm a Middletown student?",
            "I'm online only, which campus library do I use?",
            "Do all campuses have the same librarians?",
            "I'm transferring from Hamilton to Oxford, who helps me now?",
            "Can the Oxford librarian help Hamilton students?",
        ]
    },
    
    "SUBJECT_VS_COURSE_CONFUSION": {
        "description": "Mixing subject names with course codes",
        "questions": [
            "I need help with Psychology 201",  # PSY 201
            "English one eleven librarian",  # ENG 111
            "Biology two hundred level courses",
            "Chemistry one oh one guide",  # CHM 101
            "History three hundred librarian",
        ]
    },
    
    "GRADUATE_VS_UNDERGRADUATE": {
        "description": "Questions about graduate programs",
        "questions": [
            "I'm a grad student in Biology, who is my librarian?",
            "MBA program research help",
            "PhD dissertation help for Chemistry",
            "Graduate level Psychology resources",
            "Master's thesis research assistance",
        ]
    },
    
    "SPECIAL_PROGRAMS": {
        "description": "Questions about special programs or interdisciplinary studies",
        "questions": [
            "I'm in the Honors program, who is my librarian?",
            "Pre-med research help",
            "Pre-law resources",
            "Study abroad research assistance",
            "Interdisciplinary studies librarian",
            "Global and Intercultural Studies help",
            "Women's, Gender, and Sexuality Studies librarian",
        ]
    },
    
    "TIME_SENSITIVE_URGENT": {
        "description": "Urgent requests that might cause panic",
        "questions": [
            "MY PAPER IS DUE IN 1 HOUR WHO CAN HELP",
            "EMERGENCY I NEED A LIBRARIAN NOW",
            "Library closes in 10 minutes need help fast",
            "Professor rejected all my sources paper due tomorrow",
            "I'm in the library right now where do I go for help",
        ]
    },
    
    "CONTRADICTORY_REQUESTS": {
        "description": "Questions with contradictory information",
        "questions": [
            "I need help with Biology but I'm not a science major",
            "I'm taking ENG 111 but I don't need English help",
            "I want a subject librarian but don't want to talk to anyone",
            "I need research help but don't want to search for articles",
        ]
    },
    
    "TECHNICAL_JARGON": {
        "description": "Questions using advanced academic terminology",
        "questions": [
            "I need epistemological frameworks for my phenomenological study",
            "Quantitative meta-analysis resources for systematic review",
            "Hermeneutic approaches to textual analysis",
            "Poststructuralist theoretical frameworks",
            "Empirical research methodologies for mixed-methods design",
        ]
    },
    
    "NON-STANDARD_SUBJECTS": {
        "description": "Questions about subjects that might not have dedicated librarians",
        "questions": [
            "Who is the librarian for Kinesiology?",
            "I need help with Gerontology research",
            "Entrepreneurship librarian contact",
            "Family Science research guide",
            "Sport Leadership and Management help",
            "Comparative Religion librarian",
        ]
    },
    
    "MIXED_LANGUAGE": {
        "description": "Questions with non-English words or phrases",
        "questions": [
            "I need help with my investigación sobre biología",
            "Qui est le bibliothécaire pour l'anglais?",
            "Ich brauche Hilfe mit Chemie",
            "¿Dónde está la biblioteca?",
        ]
    },
    
    "EXTREME_SPECIFICITY": {
        "description": "Overly specific questions that might not match database",
        "questions": [
            "I need the librarian who specializes in 19th century British Romantic poetry with focus on Wordsworth",
            "Who helps with quantum mechanics applications in pharmaceutical development?",
            "I need resources on the socioeconomic impacts of cryptocurrency adoption in Sub-Saharan Africa",
            "Librarian for neurolinguistic programming in second language acquisition",
        ]
    },
    
    "假设性问题": {
        "description": "Hypothetical or 'what if' questions",
        "questions": [
            "What if I don't know my major yet?",
            "If I change my major, do I get a different librarian?",
            "What if my subject isn't listed?",
            "If I'm undecided, who helps me?",
            "What if I need help with multiple subjects?",
        ]
    },
}


def get_all_killer_questions():
    """Get all killer questions as a flat list."""
    all_questions = []
    for category, data in ADVANCED_KILLER_QUESTIONS.items():
        for question in data["questions"]:
            all_questions.append({
                "category": category,
                "description": data["description"],
                "question": question
            })
    return all_questions


def get_killer_questions_by_category(category):
    """Get questions for a specific category."""
    if category in ADVANCED_KILLER_QUESTIONS:
        return ADVANCED_KILLER_QUESTIONS[category]["questions"]
    return []


if __name__ == "__main__":
    # Print summary
    total = sum(len(data["questions"]) for data in ADVANCED_KILLER_QUESTIONS.values())
    print(f"Total Advanced Killer Questions: {total}")
    print(f"Categories: {len(ADVANCED_KILLER_QUESTIONS)}")
    print("\nBreakdown:")
    for category, data in ADVANCED_KILLER_QUESTIONS.items():
        print(f"  {category}: {len(data['questions'])} questions")
        print(f"    Description: {data['description']}")

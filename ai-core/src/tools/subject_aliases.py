"""
Subject Aliases and Keyword Mapping

Maps common search terms, abbreviations, and synonyms to official subject names
in the database. This ensures users can find librarians using natural language.

Based on: https://www.lib.miamioh.edu/about/organization/liaisons/
"""

# Comprehensive mapping from search terms to subject names
# Keys are lowercase search terms, values are the official Subject names in DB
SUBJECT_ALIASES = {
    # Sciences
    "chemistry": "Chemistry and Biochemistry",
    "chem": "Chemistry and Biochemistry",
    "biochemistry": "Chemistry and Biochemistry",
    "biochem": "Chemistry and Biochemistry",
    "organic chemistry": "Chemistry and Biochemistry",
    "inorganic chemistry": "Chemistry and Biochemistry",
    
    "biology": "Biology",
    "bio": "Biology",
    "biological sciences": "Biology",
    "life sciences": "Biology",
    
    "microbiology": "Microbiology",
    "micro": "Microbiology",
    
    "neuroscience": "Neuroscience",
    "neuro": "Neuroscience",
    "brain science": "Neuroscience",
    
    "physics": "Physics",
    "phys": "Physics",
    
    "environmental science": "Environmental Sciences",
    "environmental sciences": "Environmental Sciences",
    "environmental studies": "Environmental Sciences",
    "env sci": "Environmental Sciences",
    
    "geology": "Geology",
    "geo": "Geology",
    "earth science": "Geology",
    "geoscience": "Geology",
    
    "geography": "Geography",
    "geog": "Geography",
    
    # Computer Science & Engineering
    "computer science": "Computer Science and Software Engineering",
    "cs": "Computer Science and Software Engineering",
    "cse": "Computer Science and Software Engineering",
    "software engineering": "Computer Science and Software Engineering",
    "software": "Computer Science and Software Engineering",
    "programming": "Computer Science and Software Engineering",
    "coding": "Computer Science and Software Engineering",
    "compsci": "Computer Science and Software Engineering",
    
    "information systems": "Information Systems & Analytics",
    "analytics": "Information Systems & Analytics",
    "isa": "Information Systems & Analytics",
    "data analytics": "Information Systems & Analytics",
    "business analytics": "Information Systems & Analytics",
    
    "electrical engineering": "Electrical and Computer Engineering",
    "computer engineering": "Electrical and Computer Engineering",
    "ece": "Electrical and Computer Engineering",
    "ee": "Electrical and Computer Engineering",
    
    "mechanical engineering": "Mechanical and Manufacturing Engineering",
    "manufacturing engineering": "Mechanical and Manufacturing Engineering",
    "mme": "Mechanical and Manufacturing Engineering",
    "mechanical": "Mechanical and Manufacturing Engineering",
    
    "chemical engineering": "Chemical, Paper, and Biomedical Engineering",
    "biomedical engineering": "Chemical, Paper, and Biomedical Engineering",
    "paper engineering": "Chemical, Paper, and Biomedical Engineering",
    "cpb": "Chemical, Paper, and Biomedical Engineering",
    
    # Mathematics & Statistics
    "math": "Mathematics",
    "mathematics": "Mathematics",
    "mth": "Mathematics",
    "calculus": "Mathematics",
    "algebra": "Mathematics",
    
    "statistics": "Statistics",
    "stats": "Statistics",
    "sta": "Statistics",
    "statistical": "Statistics",
    
    # Business
    "business": "Business",
    "bus": "Business",
    "management": "Management",
    "mgmt": "Management",
    
    "accountancy": "Accountancy",
    "accounting": "Accountancy",
    "acc": "Accountancy",
    
    "finance": "Finance",
    "fin": "Finance",
    "financial": "Finance",
    
    "marketing": "Marketing",
    "mkt": "Marketing",
    
    "economics": "Economics",
    "econ": "Economics",
    "eco": "Economics",
    
    "entrepreneurship": "Entrepreneurship",
    "entrepreneur": "Entrepreneurship",
    
    "business legal studies": "Business Legal Studies",
    "business law": "Business Legal Studies",
    
    # Social Sciences
    "psychology": "Psychology",
    "psych": "Psychology",
    "psy": "Psychology",
    
    "sociology": "Sociology",
    "soc": "Sociology",
    
    "anthropology": "Anthropology",
    "anth": "Anthropology",
    
    "political science": "Political Science",
    "poli sci": "Political Science",
    "politics": "Political Science",
    "government": "Political Science",
    "pol": "Political Science",
    
    "criminology": "Criminology",
    "criminal justice": "Criminology",
    "crim": "Criminology",
    
    "family science": "Family Science and Social Work",
    "social work": "Family Science and Social Work",
    "fsw": "Family Science and Social Work",
    
    "gerontology": "Gerontology",
    "aging studies": "Gerontology",
    
    # Health Sciences
    "nursing": "Nursing",
    "nur": "Nursing",
    "nurse": "Nursing",
    
    "kinesiology": "Kinesiology, Nutrition, and Health",
    "nutrition": "Kinesiology, Nutrition, and Health",
    "health": "Kinesiology, Nutrition, and Health",
    "knh": "Kinesiology, Nutrition, and Health",
    "exercise science": "Kinesiology, Nutrition, and Health",
    "physical education": "Kinesiology, Nutrition, and Health",
    
    "speech pathology": "Speech Pathology and Audiology",
    "audiology": "Speech Pathology and Audiology",
    "speech therapy": "Speech Pathology and Audiology",
    "spa": "Speech Pathology and Audiology",
    
    "physician associate": "Physician Associate Studies",
    "physician assistant": "Physician Associate Studies",
    "pa studies": "Physician Associate Studies",
    
    # Humanities
    "english": "English",
    "eng": "English",
    "literature": "English",
    "writing": "English",
    
    "history": "History",
    "hist": "History",
    "his": "History",
    
    "philosophy": "Philosophy",
    "phil": "Philosophy",
    
    "religion": "Religion",
    "religious studies": "Religion",
    "rel": "Religion",
    "theology": "Religion",
    
    "classics": "Classics, Latin, and Greek",
    "latin": "Classics, Latin, and Greek",
    "greek": "Classics, Latin, and Greek",
    "classical studies": "Classics, Latin, and Greek",
    
    # Languages
    "french": "French",
    "fre": "French",
    
    "spanish": "Spanish and Portuguese",
    "portuguese": "Spanish and Portuguese",
    "spa": "Spanish and Portuguese",
    
    "german": "German",
    "ger": "German",
    
    "italian": "Italian",
    "ita": "Italian",
    
    # Area Studies
    "asian studies": "Asian/Asian-American Studies",
    "asian american studies": "Asian/Asian-American Studies",
    "asian american": "Asian/Asian-American Studies",
    
    "black world studies": "Black World Studies",
    "african american studies": "Black World Studies",
    "africana studies": "Black World Studies",
    
    "latin american studies": "Latin American Studies",
    "latin american": "Latin American Studies",
    
    "middle eastern studies": "Middle Eastern and Islamic Studies",
    "islamic studies": "Middle Eastern and Islamic Studies",
    "middle east": "Middle Eastern and Islamic Studies",
    
    "international studies": "International Studies",
    "global studies": "International Studies",
    "int studies": "International Studies",
    
    "american studies": "American Studies",
    "ams": "American Studies",
    
    "women's studies": "Women's, Gender and Sexuality Studies",
    "gender studies": "Women's, Gender and Sexuality Studies",
    "sexuality studies": "Women's, Gender and Sexuality Studies",
    "wgss": "Women's, Gender and Sexuality Studies",
    
    # Arts
    "art": "Art",
    "fine arts": "Art",
    "visual arts": "Art",
    "studio art": "Art",
    
    "music": "Music",
    "mus": "Music",
    
    "theater": "Theater",
    "theatre": "Theater",
    "drama": "Theater",
    "the": "Theater",
    
    "architecture": "Architecture & Interior Design",
    "interior design": "Architecture & Interior Design",
    "arch": "Architecture & Interior Design",
    
    "media": "Media, Journalism, and Film",
    "journalism": "Media, Journalism, and Film",
    "film": "Media, Journalism, and Film",
    "film studies": "Media, Journalism, and Film",
    "mjf": "Media, Journalism, and Film",
    
    "interactive media studies": "Interactive Media Studies / Emerging Technology in Business and Design",
    "ims": "Interactive Media Studies / Emerging Technology in Business and Design",
    "emerging technology": "Interactive Media Studies / Emerging Technology in Business and Design",
    "etbd": "Interactive Media Studies / Emerging Technology in Business and Design",
    
    # Education
    "education": "Education",
    "edu": "Education",
    "edl": "Education",
    
    "teacher education": "Teacher Education",
    "teaching": "Teacher Education",
    "edt": "Teacher Education",
    
    "educational leadership": "Educational Leadership",
    "edl": "Educational Leadership",
    
    "educational psychology": "Educational Psychology",
    "edp": "Educational Psychology",
    
    "juvenile literature": "Juvenile Literature",
    "children's literature": "Juvenile Literature",
    "kids books": "Juvenile Literature",
    
    # Special Areas
    "law": "Law",
    "legal": "Law",
    "legal studies": "Law",
    
    "government information": "Government Information and Law",
    "government documents": "Government Information and Law",
    "gov docs": "Government Information and Law",
    
    "military studies": "Military Studies",
    "military science": "Military Studies",
    "rotc": "Military Studies",
    
    "student affairs": "Student Affairs",
    "higher education": "Student Affairs",
    
    "sports leadership": "Sports Leadership and Management",
    "sports management": "Sports Leadership and Management",
    "slm": "Sports Leadership and Management",
    
    "individualized studies": "Individualized Studies - Western Program",
    "western program": "Individualized Studies - Western Program",
    "western": "Individualized Studies - Western Program",
}

# Librarian name to subjects mapping (from liaisons page)
# This allows direct search by librarian name
LIBRARIAN_SUBJECTS = {
    "ginny boehme": ["Biology", "Environmental Sciences", "Kinesiology, Nutrition, and Health", "Microbiology", "Neuroscience", "Nursing"],
    "kristen adams": ["Chemical, Paper, and Biomedical Engineering", "Chemistry and Biochemistry", "Geography", "Geology", "Mechanical and Manufacturing Engineering", "Physics"],
    "roger justus": ["Computer Science and Software Engineering", "Electrical and Computer Engineering", "Information Systems & Analytics", "Mathematics", "Statistics"],
    "roger a justus": ["Computer Science and Software Engineering", "Electrical and Computer Engineering", "Information Systems & Analytics", "Mathematics", "Statistics"],
    "megan jaskowiak": ["Criminology", "Family Science and Social Work", "Gerontology", "Physician Associate Studies", "Psychology", "Sociology", "Speech Pathology and Audiology"],
    "jenny presnell": ["American Studies", "Government Information and Law", "History", "Law", "Political Science", "Women's, Gender and Sexuality Studies"],
    "erica freed": ["Accountancy", "Business", "Economics", "Entrepreneurship", "Finance", "Management", "Marketing"],
    "abigail morgan": ["Anthropology", "Business", "Business Legal Studies", "Education", "Juvenile Literature", "Marketing", "Teacher Education"],
    "katie gibson": ["Asian/Asian-American Studies", "Black World Studies", "French", "German", "Individualized Studies - Western Program", "International Studies", "Italian", "Latin American Studies", "Middle Eastern and Islamic Studies", "Spanish and Portuguese"],
    "mark dahlquist": ["English", "Media, Journalism, and Film"],
    "rob o'brien withers": ["Classics, Latin, and Greek", "Philosophy", "Religion"],
    "rob obrien withers": ["Classics, Latin, and Greek", "Philosophy", "Religion"],
    "stefanie hilles": ["Architecture & Interior Design", "Art", "Interactive Media Studies / Emerging Technology in Business and Design", "Theater"],
    "barry zaslow": ["Music"],
    "laura birkenhauer": ["Military Studies", "Student Affairs"],
    "jaclyn spraetz": ["Educational Leadership", "Educational Psychology"],
    "andrew revelle": ["Sports Leadership and Management"],
}

# Course code to subject mapping (common course prefixes)
COURSE_CODE_SUBJECTS = {
    "CHM": "Chemistry and Biochemistry",
    "BCH": "Chemistry and Biochemistry",
    "BIO": "Biology",
    "MBI": "Microbiology",
    "NSC": "Neuroscience",
    "PHY": "Physics",
    "GLG": "Geology",
    "GEO": "Geography",
    "ENV": "Environmental Sciences",
    "CSE": "Computer Science and Software Engineering",
    "CEC": "Computer Science and Software Engineering",
    "ECE": "Electrical and Computer Engineering",
    "MME": "Mechanical and Manufacturing Engineering",
    "CPB": "Chemical, Paper, and Biomedical Engineering",
    "MTH": "Mathematics",
    "STA": "Statistics",
    "ACC": "Accountancy",
    "BUS": "Business",
    "FIN": "Finance",
    "MKT": "Marketing",
    "MGT": "Management",
    "ECO": "Economics",
    "ESP": "Entrepreneurship",
    "PSY": "Psychology",
    "SOC": "Sociology",
    "ATH": "Anthropology",
    "POL": "Political Science",
    "CJS": "Criminology",
    "FSW": "Family Science and Social Work",
    "GTY": "Gerontology",
    "NUR": "Nursing",
    "KNH": "Kinesiology, Nutrition, and Health",
    "SPA": "Speech Pathology and Audiology",
    "ENG": "English",
    "HST": "History",
    "PHL": "Philosophy",
    "REL": "Religion",
    "CLS": "Classics, Latin, and Greek",
    "LAT": "Classics, Latin, and Greek",
    "GRK": "Classics, Latin, and Greek",
    "FRE": "French",
    "SPN": "Spanish and Portuguese",
    "POR": "Spanish and Portuguese",
    "GER": "German",
    "ITA": "Italian",
    "AAS": "Asian/Asian-American Studies",
    "BWS": "Black World Studies",
    "LAS": "Latin American Studies",
    "MES": "Middle Eastern and Islamic Studies",
    "ITS": "International Studies",
    "AMS": "American Studies",
    "WGS": "Women's, Gender and Sexuality Studies",
    "ART": "Art",
    "MUS": "Music",
    "THE": "Theater",
    "ARC": "Architecture & Interior Design",
    "JRN": "Media, Journalism, and Film",
    "FST": "Media, Journalism, and Film",
    "IMS": "Interactive Media Studies / Emerging Technology in Business and Design",
    "EDL": "Educational Leadership",
    "EDP": "Educational Psychology",
    "EDT": "Teacher Education",
    "MIL": "Military Studies",
    "SLM": "Sports Leadership and Management",
}


def find_subject_by_alias(query: str) -> str | None:
    """
    Find the official subject name for a search query using aliases.
    
    Args:
        query: User's search query (lowercase)
    
    Returns:
        Official subject name if found, None otherwise
    """
    query_lower = query.lower().strip()
    
    # Direct alias match
    if query_lower in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[query_lower]
    
    # Check if query contains any alias as a substring
    for alias, subject in SUBJECT_ALIASES.items():
        if alias in query_lower or query_lower in alias:
            return subject
    
    return None


def find_subjects_by_librarian_name(name: str) -> list[str]:
    """
    Find subjects covered by a librarian name.
    
    Args:
        name: Librarian name to search for
    
    Returns:
        List of subject names the librarian covers
    """
    name_lower = name.lower().strip()
    
    # Direct match
    if name_lower in LIBRARIAN_SUBJECTS:
        return LIBRARIAN_SUBJECTS[name_lower]
    
    # Partial match (first name, last name)
    for librarian_name, subjects in LIBRARIAN_SUBJECTS.items():
        name_parts = librarian_name.split()
        if any(part in name_lower for part in name_parts):
            return subjects
    
    return []


def find_subject_by_course_code(code: str) -> str | None:
    """
    Find subject by course code prefix.
    
    Args:
        code: Course code (e.g., "CHM", "BIO 111")
    
    Returns:
        Subject name if found
    """
    # Extract the department prefix (first 2-4 letters)
    import re
    match = re.match(r'^([A-Za-z]{2,4})', code.upper())
    if match:
        prefix = match.group(1)
        return COURSE_CODE_SUBJECTS.get(prefix)
    return None


def get_all_aliases_for_subject(subject_name: str) -> list[str]:
    """
    Get all aliases that map to a subject name.
    
    Args:
        subject_name: Official subject name
    
    Returns:
        List of aliases for this subject
    """
    return [alias for alias, subj in SUBJECT_ALIASES.items() if subj == subject_name]

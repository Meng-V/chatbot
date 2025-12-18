# ULTIMATE COMPREHENSIVE TEST REPORT

**Date**: 2025-12-17 23:44:50
**Total Questions**: 124
**Test User**: Meng Qu (qum@miamioh.edu)

## 📊 Overall Statistics

| Metric | Value | Percentage |
|--------|-------|------------|
| Total Questions | 124 | 100% |
| Successful | 107 | 86.3% |
| Errors/Timeouts | 17 | 13.7% |

## 📋 Category Breakdown

### 1_LIBRARY_HOURS

**Questions**: 10 | **Success**: 10/10 (100.0%)

### 2_ROOM_RESERVATIONS

**Questions**: 10 | **Success**: 10/10 (100.0%)

- Invalid libraries rejected: 0
- Booking confirmations: 6
- Asks for missing info: 1

### 3_SUBJECT_LIBRARIANS

**Questions**: 15 | **Success**: 6/15 (40.0%)

- Responses with email: 3/6
- Responses with URL: 6/6

### 4_LIBGUIDE_SEARCHES

**Questions**: 10 | **Success**: 3/10 (30.0%)

### 5_POLICY_SERVICE

**Questions**: 12 | **Success**: 12/12 (100.0%)

### 6_PERSONAL_ACCOUNT

**Questions**: 6 | **Success**: 6/6 (100.0%)

### 7_OUT_OF_SCOPE

**Questions**: 22 | **Success**: 22/22 (100.0%)

- Properly denied: 0/22 (0.0%)
- Offered handoff: 6/22

### 8_STRESS_TESTING

**Questions**: 19 | **Success**: 19/19 (100.0%)

- Handled without errors: 19/19 (100.0%)

### 9_REGIONAL_CAMPUS

**Questions**: 6 | **Success**: 5/6 (83.3%)

### 10_EDGE_CASES

**Questions**: 14 | **Success**: 14/14 (100.0%)

## 📝 Detailed Results

### 1_LIBRARY_HOURS

#### ✅ Q1: What time does King Library close today?

**Agents**: get_library_hours

**Response**:
```
Today (Monday, December 15) King Library closes at **5:00 pm**.  
Source: King Library hours (lib.miamioh.edu)
```

**Flags**: 🔗 URL

#### ✅ Q2: When does the Art Library open tomorrow?

**Agents**: libcal

**Response**:
```
Tomorrow (Tuesday, December 16) the Wertz Art & Architecture Library opens at **8:00 am** and stays open until 5:00 pm.  
Source: LibCal [VERIFIED API DATA]
```

#### ✅ Q3: What are the hours for Rentschler Library?

**Agents**: libcal

**Response**:
```
Here are the **Rentschler Library (Hamilton) and curbside service hours** for the week of **December 15 – 21, 2025**:

• Monday, December 15: 8:00 am – 5:00 pm  
• Tuesday, December 16: 8:00 am – 5:00 pm  
• Wednesday, December 17: 8:00 am – 5:00 pm  
• Thursday, December 18: 8:00 am – 5:00 pm  
• Friday, December 19: 8:00 am – 5:00 pm  
• Saturday, December 20: Closed  
• Sunday, December 21: Closed  

Source: LibCal [VERIFIED API DATA]
```

#### ✅ Q4: Gardner-Harvey Library hours this week

**Agents**: libcal

**Response**:
```
Here are the **Gardner-Harvey Library and curbside service (Middletown)** hours for the week of **December 15–21, 2025** (source: [VERIFIED API DATA]):

• **Monday (2025-12-15):** 8:00 am – 5:00 pm  
• **Tuesday (2025-12-16):** 8:00 am – 5:00 pm  
• **Wednesday (2025-12-17):** 8:00 am – 5:00 pm  
• **Thursday (2025-12-18):** 8:00 am – 5:00 pm  
• **Friday (2025-12-19):** 8:00 am – 5:00 pm  
• **Saturday (2025-12-20):** Closed  
• **Sunday (2025-12-21):** Closed
```

#### ✅ Q5: Is the library open on Sunday?

**Agents**: get_library_hours

**Response**:
```
King Library is **closed on Sunday** for the week of December 15–21, 2025. (Source: Miami University Libraries schedule) If you need weekend access, consider our Hamilton or Middletown campuses, or contact us at (513) 529-4141 or visit https://www.lib.miamioh.edu for more details.
```

**Flags**: 🔗 URL

#### ✅ Q6: What time does the makerspace close?

**Agents**: search_website

**Response**:
```
The Miami University Makerspace in King Library follows the library’s third-floor service hours. During the regular semester those are:

• Monday–Thursday: 8 AM–11 PM  
• Friday: 8 AM–7 PM  
• Saturday: 10 AM–7 PM  
• Sunday: 1 PM–11 PM  

These hours vary slightly between semesters and breaks. For the most up-to-date schedule, check the Makerspace guide: https://libguides.lib.miamioh.edu/create/makerspace
```

**Flags**: 🔗 URL

#### ✅ Q7: Special Collections hours

**Agents**: libcal

**Response**:
```
Here are the Walter Havighurst Special Collections & University Archives hours for the week of December 15–21, 2025 (Source: LibCal [VERIFIED API DATA]):

• Monday (2025-12-15): Closed  
• Tuesday (2025-12-16): Closed  
• Wednesday (2025-12-17): Closed  
• Thursday (2025-12-18): Closed  
• Friday (2025-12-19): Closed  
• Saturday (2025-12-20): Closed  
• Sunday (2025-12-21): Closed  

If you need hours for a different week or have other questions about Special Collections, I’d be happy to connec
```

**Flags**: 🔗 URL

#### ✅ Q8: Hamilton campus library hours

**Agents**: libcal

**Response**:
```
Here are the Rentschler Library (Hamilton) hours for the week of December 15, 2025, according to LibCal:

• **Monday (12 / 15):** 8:00 am – 5:00 pm  
• **Tuesday (12 / 16):** 8:00 am – 5:00 pm  
• **Wednesday (12 / 17):** 8:00 am – 5:00 pm  
• **Thursday (12 / 18):** 8:00 am – 5:00 pm  
• **Friday (12 / 19):** 8:00 am – 5:00 pm  
• **Saturday (12 / 20):** Closed  
• **Sunday (12 / 21):** Closed  

If you need hours for a different week or have other questions, please let me know!
```

#### ✅ Q9: Middletown library schedule

**Agents**: get_library_hours

**Response**:
```
Here are the **Gardner-Harvey Library (Middletown campus)** hours for the week of **December 15–21, 2025** (including curbside service):  
• **Monday (Dec 15)**: 8 am–5 pm  
• **Tuesday (Dec 16)**: 8 am–5 pm  
• **Wednesday (Dec 17)**: 8 am–5 pm  
• **Thursday (Dec 18)**: 8 am–5 pm  
• **Friday (Dec 19)**: 8 am–5 pm  
• **Saturday (Dec 20)**: Closed  
• **Sunday (Dec 21)**: Closed  

(Source: Miami University Libraries hours tool)
```

#### ✅ Q10: Are libraries open during finals week?

**Agents**: search_website

**Response**:
```
Yes—during finals week (Saturday, May 12 through Friday, May 18), Miami University Libraries extend their hours to give you more study time. Here’s the schedule from the Libraries’ announcement:

• **King Library**  
  – May 12–13: open 24 hours  
  – May 14–17: open 24 hours  
  – May 18: closes at 5 p.m.

• **B.E.S.T. Library** (Business, Education & Social Sciences)  
  – May 12: 9 a.m.–10 p.m.  
  – May 13: 9 a.m.–2 a.m.  
  – May 14–17: 7:30 a.m.–2 a.m.  
  – May 18: 7:30 a.m.–5 p.m.

• **W
```

**Flags**: 🔗 URL

### 2_ROOM_RESERVATIONS

#### ✅ Q1: Book a study room at King Library for tomorrow 2pm-4pm for 4 people. Name: Meng Qu, Email: qum@miamioh.edu

**Agents**: book_room

**Response**:
```
I’m sorry—the booking for **King Library** tomorrow from **2 pm–4 pm** can’t be completed because it exceeds the **120-minute per-day limit** at that location. Would you like to:

• Book a shorter time slot?  
• Try a different library?  

Let me know which option works for you!
```

**Flags**: ✅ Confirmation

#### ✅ Q2: I need to reserve a room at Art Library on 12/18/2025 from 10am to 12pm for 2 people. Meng Qu, qum@miamioh.edu

**Agents**: book_room

**Response**:
```
I’m sorry, but it looks like Art & Architecture Library study rooms can only be booked for up to **2 hours (120 minutes) per day**, and your requested time slot is exactly 2 hours. It seems our system interpreted this as exceeding the limit. 

Would you like to:
• Adjust the reservation to a shorter duration (for example, 11am–12pm)?  
• Try a different library location (King Library, Rentschler Library, Gardner-Harvey Library)?  

Let me know what you’d like to do!
```

#### ✅ Q3: Check room availability at King Library tomorrow 3pm-5pm for 3 people

**Agents**: search_rooms

**Response**:
```
Sure—before I check availability, I just need a few more details:

• Your first name  
• Your last name  
• Your Miami University email (ending in @miamioh.edu)  

Once I have those, I can complete the booking search for King Library tomorrow from 3 PM to 5 PM for 3 people.
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q4: Are there any study rooms available at Rentschler Library tomorrow afternoon?

**Agents**: None

**Response**:
```
Sure—let’s get you the most accurate availability. For tomorrow afternoon at Rentschler Library, could you let me know:

• What time you’d like your booking to start and end (e.g., 1:00 PM to 3:00 PM)  
• How many people will be in your group  

Once I have those details, I can check which rooms are open.
```

**Flags**: ✅ Confirmation

#### ✅ Q5: Book a study room at Farmer Library tomorrow

**Agents**: None

**Response**:
```
I’m sorry, but **Farmer Library doesn’t offer study rooms** for booking. The libraries that do are:  
• **King Library** (Oxford campus)  
• **Art & Architecture Library** (Oxford campus)  
• **Rentschler Library** (Hamilton campus)  
• **Gardner-Harvey Library** (Middletown campus)  

Which of these would you like to book, and could you please provide your full name, @miamioh.edu email, date, time range, and number of people?
```

**Flags**: 📧 Email | ✅ Confirmation | ❓ Asks Info

#### ✅ Q6: Reserve a room at Science Library

**Agents**: None

**Response**:
```
I’m sorry, but the Science Library doesn’t offer reservable study rooms. We have study rooms at these four libraries:  
• **King Library** (Oxford campus)  
• **Art & Architecture Library** (Oxford campus)  
• **Rentschler Library** (Hamilton campus)  
• **Gardner-Harvey Library** (Middletown campus)  

Which of these would you like to book a room in?
```

#### ✅ Q7: I want to book the Law Library study room

**Agents**: None

**Response**:
```
The Law Library doesn’t offer reservable study rooms. The four campus libraries that do are:

• **King Library** (Oxford campus)  
• **Art & Architecture Library** (Oxford campus)  
• **Rentschler Library** (Hamilton campus)  
• **Gardner-Harvey Library** (Middletown campus)  

Which of these would you like to book a room in?
```

#### ✅ Q8: I need to book a study room

**Agents**: None

**Response**:
```
Sure—let’s get your reservation set up! To book a study room I’ll need:

• Which library: **King (Oxford)**, **Art & Architecture (Oxford)**, **Rentschler (Hamilton)**, or **Gardner-Harvey (Middletown)**  
• Your full name (first and last)  
• Your @miamioh.edu email address  
• Date of booking (e.g., 11/12/2025, tomorrow, next Monday)  
• Start and end times (e.g., 2 pm–4 pm)  
• Number of people in your group  

Once you send those details I can complete the booking for you!
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q9: Reserve a room for tomorrow

**Agents**: None

**Response**:
```
Sure—I'd be happy to help you reserve a study room for tomorrow. To complete your booking, I just need a few details:

• Your **first name**  
• Your **last name**  
• Your **@miamioh.edu email address**  
• **Which library** (please choose one):  
  • King Library (Oxford campus)  
  • Art & Architecture Library (Oxford campus)  
  • Rentschler Library (Hamilton campus)  
  • Gardner-Harvey Library (Middletown campus)  
• Your desired **start time** and **end time**  
• **Number of people** in 
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q10: Book King Library room

**Agents**: None

**Response**:
```
Sure—let’s get your King Library study room booked! I just need a few details:

• First name  
• Last name  
• Your @miamioh.edu email address  
• Date you’d like to book (e.g., “April 10, 2024” or “next Tuesday”)  
• Start time and end time (e.g., “2 pm to 4 pm”)  
• Number of people in your group  

Once I have those, I can confirm your reservation.
```

**Flags**: 📧 Email

### 3_SUBJECT_LIBRARIANS

#### ✅ Q1: Who is the biology librarian?

**Agents**: subject_librarian

**Response**:
```
For biology research help, you can reach out to **Ginny Boehme**, Science Librarian:

• **Email:** boehmemv@miamioh.edu  
• **Phone:** (513) 529-1726  

Need more assistance? Chat with a librarian any time: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 📧 Email | 🔗 URL | 👋 Handoff

#### ✅ Q2: I need help with my English paper

**Agents**: google_site

**Response**:
```
Here are a few Miami University Libraries resources to help with your English paper:

• **Literatures in English LibGuide** – a subject guide with overviews, recommended databases, and research strategies tailored to English studies  
  https://libguides.lib.miamioh.edu/english  

• **ENG 298: Citing Your Sources and Academic Integrity** – guidance on citation styles, avoiding plagiarism, and managing your references  
  https://libguides.lib.miamioh.edu/ENG298/citations  

If you’d like one-on-
```

**Flags**: 🔗 URL | 👋 Handoff

#### ❌ Q3: Psychology department librarian contact

**Error**: 

#### ❌ Q4: Who can help me with chemistry research?

**Error**: 

#### ❌ Q5: Business librarian email

**Error**: 

#### ❌ Q6: History subject librarian

**Error**: 

#### ✅ Q7: I'm taking ENG 111, who is my librarian?

**Agents**: subject_librarian

**Response**:
```
For ENG 111 research support, you can contact the English subject librarian:

• **Mark Dahlquist**, Humanities and Social Sciences Librarian  
  Email: dahlqumj@miamioh.edu  
  Phone: (513) 529-8494  

Need additional help? Chat with a librarian: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 📧 Email | 🔗 URL | 👋 Handoff

#### ❌ Q8: PSY 201 librarian contact

**Error**: 

#### ✅ Q9: Who helps with BIO courses?

**Agents**: find_subject_librarian

**Response**:
```
For biology courses, contact **Ginny Boehme** (Science Librarian). You can reach her at **boehmemv@miamioh.edu** or (513) 529-1726. 

View her subject guide for biology: https://libguides.lib.miamioh.edu/biology 

If you need further assistance, you can also chat with a librarian: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 📧 Email | 🔗 URL | 👋 Handoff

#### ❌ Q10: Music librarian at Miami

**Error**: 

#### ✅ Q11: Art history research help

**Agents**: find_subject_librarian

**Response**:
```
For Art History research, please reach out to:

• **Stefanie Hilles**, Arts & If you’d like more general research assistance or don’t hear back promptly, you can chat with a librarian anytime at https://www.lib.miamioh.edu/research/research-support/ask/ or call **(513) 529-4141**.

⚠️ **Note**: Some contact information could not be verified. For accurate contact details, visit https://www.lib.miamioh.edu/research/research-support/ask/ or call (513) 529-4141.
```

**Flags**: 🔗 URL | 👋 Handoff

#### ❌ Q12: Political science librarian

**Error**: 

#### ❌ Q13: Who is the librarian at Hamilton campus?

**Error**: 

#### ✅ Q14: Middletown campus librarian contact

**Agents**: search_website

**Response**:
```
For general library assistance on the Middletown campus, please contact **Gardner-Harvey Library**:

• Phone: **(513) 727-3222**  
• Address: 4200 N. University Blvd., Middletown, OH 45042  

If you need research help or don’t have a specific librarian in mind, you can also submit your question online via Ask a Librarian:  
https://www.lib.miamioh.edu/research/research-support/ask/  

Source: Regional Libraries | Miami University Libraries (lib.miamioh.edu)
```

**Flags**: 🔗 URL | 👋 Handoff

#### ❌ Q15: I'm a nursing major, who is my librarian?

**Error**: 

### 4_LIBGUIDE_SEARCHES

#### ❌ Q1: Research guide for biology

**Error**: 

#### ✅ Q2: Find guide for ENG 111

**Agents**: find_course_guide

**Response**:
```
For ENG 111 questions, contact **Mark Dahlquist** (dahlqumj@miamioh.edu). View the subject guide here: https://libguides.lib.miamioh.edu/sb.php?subject_id=8447
```

**Flags**: 📧 Email | 🔗 URL

#### ❌ Q3: Psychology research resources

**Error**: 

#### ❌ Q4: Business LibGuide

**Error**: 

#### ❌ Q5: Chemistry research guide

**Error**: 

#### ❌ Q6: History primary sources guide

**Error**: 

#### ✅ Q7: Where can I find nursing resources?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ❌ Q8: Political science databases

**Error**: 

#### ✅ Q9: Art history research guide

**Agents**: find_subject_librarian

**Response**:
```
For art history research help, please reach out to:

• **Stefanie Hilles**, Arts & Humanities Librarian  
  Email: **hillessa@miamioh.edu**  
  Phone: **(513) 529-6650**  

Need additional support or resources? Chat with a librarian anytime:  
https://www.lib.miamioh.edu/research/research-support/ask/  

Source: Miami University Libraries subject librarians tool.
```

**Flags**: 📧 Email | 🔗 URL | 👋 Handoff

#### ❌ Q10: Music research resources

**Error**: 

### 5_POLICY_SERVICE

#### ✅ Q1: How do I renew a book?

**Agents**: None

**Response**:
```
I can't renew books or check renewal status directly. Please renew online at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact a librarian for help.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q2: What are the late fees for overdue books?

**Agents**: search_website

**Response**:
```
Here’s a quick breakdown of overdue‐book fines at Miami University Libraries:  
• **University-owned books** (Oxford, Hamilton, Middletown)  
  – $0.25 per day, per item  
  – Maximum fine: $10.00 per item  

• **OhioLINK books**  
  – $1.00 per day, per item  
  – No maximum fine cap  

For full details on loan periods, fine schedules and billing procedures, please see the Circulation Policies page:  
https://libguides.lib.miamioh.edu/circulation-policies/loan-periods-fines  

Source: Circulati
```

**Flags**: 🔗 URL

#### ✅ Q3: Can I eat in the library?

**Agents**: google_site

**Response**:
```
I’m not seeing a specific food‐and‐drink policy in our available resources. For the most accurate information, please reach out to a librarian:

• Call: (513) 529-4141  
• Chat or email: https://www.lib.miamioh.edu/research/research-support/ask/

They’ll be happy to let you know where eating is (or isn’t) allowed.
```

**Flags**: 🔗 URL

#### ✅ Q4: How do I print in the library?

**Agents**: search_website

**Response**:
```
You can print from any Miami University Libraries printer in two simple steps:

• Get your document into the MUprint queue  
  – From your computer or device, choose “MUprint Black and White” or “MUprint Color” as your printer  
  – Email a PDF or image file to MUprint-BW@MiamiOH.edu (black & white) or MUprint-Color@MiamiOH.edu (color)  
  – Or upload your file at MUprint.MiamiOH.edu  

• Release your job at the printer  
  – Scan the QR code on the printer with your phone to open the release we
```

**Flags**: 🔗 URL

#### ✅ Q5: What is the library's guest policy?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q6: How do I get a library card?

**Agents**: search_website

**Response**:
```
To get a Miami University Libraries card, follow these steps:

• If you’re a Miami student, faculty or staff member, your valid Miami University ID serves as your library card—simply bring it to any campus library to borrow materials.  
• If you’re an Oxford community member, you can apply in person at King Library (325 S. Patterson Ave., Oxford, OH). Bring a government-issued photo ID plus proof of local address (e.g., utility bill).  
• If you’re a regional campus community member (Hamilton or
```

**Flags**: 🔗 URL

#### ✅ Q7: Can I check out equipment?

**Agents**: google_site

**Response**:
```
Yes—you can borrow a variety of tech gear from Miami University Libraries. Here’s how it works:

• Bring your **Miami University ID** to any library checkout desk.  
• Call ahead at **(513) 529-4141** to confirm availability—items do go out or get returned late.  
• Typical loan periods:  
  – Chromebook laptops: 30 days  
  – Tablets, cameras & camcorders: 24 hours  
• Available items include:  
  – Laptops & tablets (Chromebooks, iPad Pros + Apple Pencils at Art & Architecture Library)  
  – A
```

**Flags**: 🔗 URL

#### ✅ Q8: What cameras are available to borrow?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q9: Interlibrary loan policy

**Agents**: None

**Response**:
```
I can't manage ILL requests. Please visit https://lib.miamioh.edu/use/borrow/ill/ or contact a librarian for ILL help.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q10: How long can I keep a book?

**Agents**: search_website

**Response**:
```
Miami University Libraries’ standard loan periods for printed books (Miami-owned items) are:  
• **Undergraduate students & alumni**: 28 days  
• **Graduate students & staff**: 84 days  
• **Faculty**: 120 days  

Most books can be renewed up to three times (online via your library account or at the Circulation Desk) unless another patron places a hold.  

For full details on loan periods, renewals, fines and recalls, see the **Loan Periods, Fines and Charges** guide:  
https://libguides.lib.mia
```

**Flags**: 🔗 URL

#### ✅ Q11: Can I reserve a laptop?

**Agents**: search_website

**Response**:
```
Yes—Miami University Libraries lets you reserve laptops through our Equipment Checkout service. To place a hold:

• Go to https://www.lib.miamioh.edu/ and pick “Laptop”  
• Sign in with your Miami credentials, select your pickup location (King Library or your regional campus), date and time  
• You’ll receive a confirmation email once your reservation is complete  

If you need help, stop by the Service Desk, call us at **(513) 529-4141**, or submit a question online: https://www.lib.miamioh.edu
```

**Flags**: 🔗 URL | ✅ Confirmation

#### ✅ Q12: What is the quiet study policy?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

### 6_PERSONAL_ACCOUNT

#### ✅ Q1: Check my library account

**Agents**: None

**Response**:
```
I don't have access to your library account. Please check your account at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact us at (513) 529-4141.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q2: How do I access my account?

**Agents**: None

**Response**:
```
I don't have access to your library account. Please check your account at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact us at (513) 529-4141.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q3: View my checked out books

**Agents**: None

**Response**:
```
To see your currently checked-out items, please:

• Go to the Miami University Libraries website at https://www.lib.miamioh.edu  
• Click on **My Account** (top right corner) and sign in with your Miami University credentials  
• Once logged in, select the **Checked Out** tab to view and renew your loans

If you have trouble logging in or need assistance, you can call the Library at (513) 529-4141 or submit a question at https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q4: My library fines

**Agents**: None

**Response**:
```
I don't have access to your library account. Please check your account at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact us at (513) 529-4141.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q5: Renew my books online

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q6: Check my holds

**Agents**: None

**Response**:
```
**My Library Account**

To view your personal library account information (loans, fines, requests, holds, messages), please sign in to your account:

🔗 **[Access My Library Account](https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en)**

From your account you can:
• View your current **loans** and due dates
• Check any **fines or fees**
• See your **requests** and holds
• View **blocks** or messages on your account
• Update your **personal 
```

**Flags**: ❓ Asks Info

### 7_OUT_OF_SCOPE

#### ✅ Q1: What's the weather today?

**Agents**: google_site

**Response**:
```
I’m sorry, but I don’t have information on today’s weather. For library-related questions, you can reach us at (513) 529-4141 or via our Ask-a-Librarian chat: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q2: Will it rain tomorrow?

**Agents**: google_site

**Response**:
```
I’m sorry, but I can’t help with weather forecasts. I specialize in Miami University Libraries information—if you need library assistance, please call (513) 529-4141 or chat with us at https://www.lib.miamioh.edu/research/research-support/ask/.
```

**Flags**: 🔗 URL | ❓ Asks Info

#### ✅ Q3: How do I register for classes?

**Agents**: google_site

**Response**:
```
For general university questions like class registration, please visit miamioh.edu or contact the university at (513) 529-1809.
```

#### ✅ Q4: When is course registration?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q5: Can you help me add a class?

**Agents**: google_site

**Response**:
```
I’m afraid class registration falls outside the library’s services. Please contact your academic advisor for help adding a class.
```

#### ✅ Q6: What's for lunch at the dining hall?

**Agents**: google_site

**Response**:
```
I’m sorry, but dining hall menus fall outside the library’s scope. For information about campus dining, please visit miamioh.edu or contact the university at (513) 529-1809.
```

#### ✅ Q7: Where can I eat on campus?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q8: Dining hall hours

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q9: When is the football game?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q10: Basketball schedule

**Agents**: google_site

**Response**:
```
I’m sorry, but basketball schedules fall outside the Library’s scope. For general university information, please visit miamioh.edu or contact the university at (513) 529-1809.
```

#### ✅ Q11: Can you help me with my math homework?

**Agents**: google_site

**Response**:
```
I’m sorry, but I can’t help with course‐specific math homework. For assistance with your math questions, please contact your professor or your academic department. If you need help finding library resources or research support, you can reach the Miami University Libraries at (513) 529-4141 or via our Ask-a-Librarian service: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q12: What's the answer to question 5?

**Agents**: None

**Response**:
```
I’m not sure which “question 5” you’re referring to—could you please share the full text or context of that question? Once I know what it asks, I can help you find the answer or point you to the right resources.
```

#### ✅ Q13: Write my essay for me

**Agents**: None

**Response**:
```
I’m happy to help you get started, but I can’t write the essay for you. Instead, let’s work together on:

• Clarifying your assignment prompt and topic  
• Developing a strong thesis statement  
• Creating an outline to organize your ideas  
• Finding and evaluating credible library sources  

Could you share more about your essay’s topic, course, or any guidelines you’ve been given? Once I know your subject area, I can point you to research guides, relevant databases, and even put you in touch 
```

#### ✅ Q14: Where is the student center?

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q15: How do I get to Armstrong?

**Agents**: google_site

**Response**:
```
I’m sorry, I don’t have that information from our library systems. For help finding Armstrong, please contact the Miami University Libraries:  
• Phone: **(513) 529-4141**  
• Ask-a-Librarian chat: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ✅ Q16: Campus map

**Agents**: search_website

**Response**:
```
I’m sorry, our search service is temporarily unavailable. For a campus map and directions, please visit the Miami University Libraries website at https://www.lib.miamioh.edu or give us a call at **(513) 529-4141**.
```

**Flags**: 🔗 URL

#### ✅ Q17: How do I connect to WiFi?

**Agents**: search_website

**Response**:
```
Here’s how to get online in any Miami University library:

• **Students & Employees**  
    • Select the eduroam network  
    • Log in with your full Miami University  and your university password  

• **Visitors & Guests**  
    • Select the MiamiU-Guest network  
    • Follow the on-screen prompts to register and agree to the acceptable-use policy  

If you run into trouble, stop by any library service desk or call us at **(513) 529-4141**. You can also find more details at https://www.lib.mi
```

**Flags**: 🔗 URL

#### ✅ Q18: My laptop is broken

**Agents**: google_site

**Response**:
```
It sounds like you need IT support rather than library assistance. Please contact IT Services at .

⚠️ **Note**: Some contact information could not be verified. For accurate contact details, visit https://www.lib.miamioh.edu/research/research-support/ask/ or call (513) 529-4141.
```

**Flags**: 🔗 URL | ❓ Asks Info

#### ✅ Q19: Canvas login issues

**Agents**: search_website

**Response**:
```
I’m sorry you’re having trouble logging into Canvas. Canvas support is handled by Miami University’s IT Service Desk rather than the library. Please reach out to the IT Service Desk through your Miami University portal or search “Miami University IT Service Desk” for their contact details. 

If you have other library‐related questions, feel free to call us at **(513) 529-4141** or visit our website at https://www.lib.miamioh.edu.
```

**Flags**: 🔗 URL

#### ✅ Q20: How do I pay tuition?

**Agents**: google_site

**Response**:
```
I’m sorry, but I only handle Miami University Libraries questions. For general University matters like paying tuition, please visit miamioh.edu or contact the University at (513) 529-1809.
```

#### ✅ Q21: Financial aid office hours

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q22: Scholarship information

**Agents**: google_site

**Response**:
```
It looks like scholarship inquiries fall under University Financial Aid rather than the Libraries. For general university questions—including scholarships—please visit miamioh.edu or call the University at (513) 529-1809.
```

### 8_STRESS_TESTING

#### ✅ Q1: I need to find a book about psychology and also I want to know the library hours and can you help me with my research paper and I also need to book a study room for tomorrow and I'm not sure what time but probably in the afternoon maybe around 2 or 3 pm and I need it for about 2 hours and there will be 4 people in my group and my name is Meng Qu and my email is qum@miamioh.edu and I'm a psychology major and I need help finding sources for my paper on cognitive development

**Agents**: None

**Response**:
```
Catalog search is currently unavailable. Please search directly at https://www.lib.miamioh.edu/ or chat with a librarian who can help find materials.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL | 👋 Handoff

#### ✅ Q2: '; DROP TABLE users; --

**Agents**: None

**Response**:
```
Hi there! It looks like you’ve entered some code that resembles an SQL injection snippet. How can I help you today? If you’re looking for assistance with library resources, research support, study rooms, or anything else, just let me know!
```

#### ✅ Q3: 1' OR '1'='1

**Agents**: None

**Response**:
```
Hi there! It looks like you’ve entered a string often used in programming or databases. How can I help you today with library resources or services?
```

#### ✅ Q4: <script>alert('xss')</script>

**Agents**: None

**Response**:
```
Hello! It looks like you entered some code—how can I assist you today with library resources or services? If you have questions about books, study rooms, research guides, or anything else, just let me know!
```

#### ✅ Q5: What are the hours for King Library?!@#$%^&*()

**Agents**: libcal

**Response**:
```
Here are the **King Library** hours for the week of **December 15–21, 2025** (Source: LibCal [VERIFIED API DATA]):

• **Monday (12/15/2025):** 8:00 am – 5:00 pm  
• **Tuesday (12/16/2025):** 8:00 am – 5:00 pm  
• **Wednesday (12/17/2025):** 8:00 am – 5:00 pm  
• **Thursday (12/18/2025):** 8:00 am – 5:00 pm  
• **Friday (12/19/2025):** 8:00 am – 5:00 pm  
• **Saturday (12/20/2025):** Closed  
• **Sunday (12/21/2025):** Closed
```

#### ✅ Q6: Book room @#$%

**Agents**: None

**Response**:
```
Sure—let’s get your study room booked! I just need a few details:

• Your first and last name  
• Your @miamioh.edu email address  
• Date you’d like to reserve (e.g., “December 1” or “12/1/2025”)  
• Start time and end time (e.g., “2 pm–4 pm”)  
• Number of people in your group  
• Which library: King (Oxford), Art & Architecture (Oxford), Rentschler (Hamilton), or Gardner-Harvey (Middletown)  

Once I have all of that, I can complete your booking.
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q7: Librarian contact: <test@test.com>

**Agents**: None

**Response**:
```
I’m not finding a subject librarian associated with that email address. To help you connect with the right librarian, could you please tell me what subject or course you need assistance with?  

If you need immediate help or aren’t sure whom to contact, you can also:  
• Visit our Ask a Librarian page: https://www.lib.miamioh.edu/research/research-support/ask/  
• Call the library at **(513) 529-4141**  

Let me know your subject area or course, and I’ll look up the correct librarian for you!
```

**Flags**: 🔗 URL | 👋 Handoff

#### ✅ Q8:    

**Agents**: None

**Response**:
```
Hello! Welcome to Miami University Libraries. How can I help you today? Whether you need to find resources, book a study room, or get research assistance, I’m here to help.
```

#### ✅ Q9: 

**Agents**: None

**Response**:
```
Hello! How can I assist you today with Miami University Libraries? Whether you need help finding resources, booking a study room, or connecting with a subject librarian, just let me know.
```

**Flags**: ✅ Confirmation

#### ✅ Q10: 




**Agents**: None

**Response**:
```
Hello! How can I assist you today with Miami University Libraries?
```

#### ✅ Q11: 图书馆几点关门？

**Agents**: get_library_hours

**Response**:
```
King 图书馆（Oxford 校区）的本周开放时间如下：

• 周一至周五：上午 8:00 至 下午 5:00  
• 周六、周日：闭馆  

信息来源：Miami University Libraries 官网。
```

#### ✅ Q12: ¿Cuándo cierra la biblioteca?

**Agents**: get_library_hours

**Response**:
```
La **King Library** cierra a las **5:00 pm** de lunes a viernes y está cerrada sábados y domingos esta semana. (Fuente: LibCal)
```

#### ✅ Q13: asdfghjkl qwertyuiop

**Agents**: None

**Response**:
```
I’m sorry, I didn’t quite catch that. Could you please clarify your question or let me know how I can help you with Miami University Libraries?
```

#### ✅ Q14: blah blah blah

**Agents**: None

**Response**:
```
Hello! How can I help you today? For example, I can assist with:  
• Finding books, articles, or e-resources in our catalog  
• Booking a study room at one of our libraries  
• Connecting you with a subject librarian or research guide  
• Checking library hours or policies  

Just let me know what you need, and I’ll be happy to assist!
```

**Flags**: ✅ Confirmation

#### ✅ Q15: test test test 123

**Agents**: None

**Response**:
```
Hello! How can I assist you today? If you have questions about our services, need help finding resources, or want to book a study room, just let me know.
```

#### ✅ Q16: Book a room for yesterday

**Agents**: None

**Response**:
```
I’m sorry, but we can’t make reservations for past dates. Could you please let me know the following for a future booking?  

• Your first and last name  
• Your @miamioh.edu email address  
• The date you’d like to reserve (must be today or later)  
• Start and end times  
• Number of people in your group  
• Which library: **King**, **Art & Architecture**, **Rentschler**, or **Gardner-Harvey**  

Once I have those details, I can set up your room reservation.
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q17: What time does the library close before it opens?

**Agents**: None

**Response**:
```
Could you clarify which Miami University library location you mean? We have four with public hours:

• **King Library** (Oxford campus)  
• **Art & Architecture Library** (Oxford campus)  
• **Rentschler Library** (Hamilton campus)  
• **Gardner-Harvey Library** (Middletown campus)  

Let me know which one, and I can share its closing (and opening) times.
```

#### ✅ Q18: I need a study room at King Library on December 25th, 2025 at 3:47 AM for exactly 73 minutes for 0.5 people

**Agents**: None

**Response**:
```
I can help you reserve a King Library study room on December 25, 2025 beginning at 3:47 AM for a 73-minute block (that ends at 5:00 AM). To complete your booking I just need a few details:

• Your first name  
• Your last name  
• Your @miamioh.edu email address  
• The number of people in your group (we require a whole number, minimum 1)  

Once I have those, I can finalize your reservation. Let me know!
```

**Flags**: 📧 Email | ✅ Confirmation

#### ✅ Q19: What are the hours? Who is the librarian? Can I book a room? How do I renew?

**Agents**: None

**Response**:
```
I can't renew books or check renewal status directly. Please renew online at https://ohiolink-mu.primo.exlibrisgroup.com/discovery/account?vid=01OHIOLINK_MU:MU&section=overview&lang=en or contact a librarian for help.

⏰ **Live chat is currently closed**
Chat hours today: 9:00am - 5:00pm
Submit a ticket for off-hours help: https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

### 9_REGIONAL_CAMPUS

#### ✅ Q1: I'm at Hamilton campus, what are the library hours?

**Agents**: libcal

**Response**:
```
For the week of December 15–21, 2025, Rentschler Library and curbside service (Hamilton) hours are:  
• Monday (12/15) – Friday (12/19): 8:00 am to 5:00 pm  
• Saturday (12/20) – Sunday (12/21): Closed  

Source: [VERIFIED API DATA] If you need hours for a different week or have any questions, please call the library at (513) 529-4141 or visit https://www.lib.miamioh.edu/research/research-support/ask/
```

**Flags**: 🔗 URL

#### ❌ Q2: Who is the librarian at Rentschler Library?

**Error**: 

#### ✅ Q3: Book a room at Hamilton

**Agents**: None

**Response**:
```
Sure—let’s get your Rentschler Library (Hamilton campus) study room booked. Could you please provide:  
• Your first and last name  
• Your @miamioh.edu email address  
• The date you’d like to reserve  
• Start time and end time  
• Number of people in your group  

Once I have those details, I’ll confirm your booking and send you the confirmation number.
```

**Flags**: 📧 Email | ✅ Confirmation | ❓ Asks Info

#### ✅ Q4: Middletown campus library contact

**Agents**: search_website

**Response**:
```
For the Gardner-Harvey Library (Middletown campus), you can reach us by phone or online:  
• Phone: **(513) 529-4141**  
• Submit a question online: https://www.lib.miamioh.edu/research/research-support/ask/  

Source: General Miami University Libraries contact information.
```

**Flags**: 🔗 URL

#### ✅ Q5: Gardner-Harvey Library hours

**Agents**: libcal

**Response**:
```
Here are the **Gardner‐Harvey Library and curbside service (Middletown)** hours for the week of December 15–21, 2025 (source: [VERIFIED API DATA]):

• **Monday (2025-12-15):** 8:00 am to 5:00 pm  
• **Tuesday (2025-12-16):** 8:00 am to 5:00 pm  
• **Wednesday (2025-12-17):** 8:00 am to 5:00 pm  
• **Thursday (2025-12-18):** 8:00 am to 5:00 pm  
• **Friday (2025-12-19):** 8:00 am to 5:00 pm  
• **Saturday (2025-12-20):** Closed  
• **Sunday (2025-12-21):** Closed
```

#### ✅ Q6: I'm at Middletown, who can help me with research?

**Agents**: None

**Response**:
```
For research help at the Middletown campus (Gardner-Harvey Library), you have a couple of easy options:  
• Submit your question via our online research support form: https://www.lib.miamioh.edu/research/research-support/ask/  
• Give us a call at **(513) 529-4141** and ask for the Gardner-Harvey Library staff  

Our librarians will be happy to connect you with the right subject specialist or walk you through databases, citation help, and more.
```

**Flags**: 🔗 URL

### 10_EDGE_CASES

#### ✅ Q1: hours

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q2: librarian

**Agents**: connect_librarian

**Response**:
```
Here’s how you can get in touch with a Miami University librarian right now:

• Live chat is **closed** (today’s hours: 9:00 am – 5:00 pm).  
• To submit a question anytime, use our online form: https://www.lib.miamioh.edu/research/research-support/ask/  
• If you prefer phone support, call **(513) 529-4141** during library hours.  

Feel free to drop back in during chat hours for live help!
```

**Flags**: 🔗 URL

#### ✅ Q3: book

**Agents**: None

**Response**:
```
Sure—could you clarify what you’d like to book?  
• If you want to reserve a **study room**, let me know which campus library (King, Art & Architecture, Rentschler, or Gardner-Harvey) plus your full name, @miamioh.edu email, date, start/end times, and number of people.  
• If you’re looking for a **book** to borrow, please share the title, author, or subject so I can search our catalog.
```

**Flags**: 📧 Email

#### ✅ Q4: help

**Agents**: None

**Response**:
```
Hello! I’m the Miami University Libraries virtual assistant. I can help you with a variety of services, including:

• **Finding books, articles & e-resources** – just tell me what you need or ask me to search the catalog  
• **Checking library hours** – for King, Art & Architecture, Rentschler or Gardner-Harvey  
• **Booking a study room** – in any of our four libraries (King, Art & Architecture, Rentschler, Gardner-Harvey)  
• **Connecting with your subject librarian** – for research guidance i
```

**Flags**: 🔗 URL | ✅ Confirmation

#### ✅ Q5: libary hours

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q6: libraian contact

**Agents**: None

**Response**:
```
Here’s how to connect with a librarian at Miami University Libraries:

• **Phone**: (513) 529-4141  
• **Research Support / Ask Us**: Submit your question online and get live chat, email or text help  
  https://www.lib.miamioh.edu/research/research-support/ask/  
• **LibAnswers Chat**: 24/7 chat with a librarian  
  https://libanswers.lib.miamioh.edu/

If you need a subject‐specific librarian (e.g., for Biology, Business, English, etc.), let me know your discipline and I can point you to the ri
```

**Flags**: 🔗 URL | 👋 Handoff

#### ✅ Q7: resereve room

**Agents**: None

**Response**:
```
Sure—let’s get your study room reserved! I’ll need a few details:

• Which library? (choose one)  
  – **King Library** (Oxford campus)  
  – **Art & Architecture Library** (Oxford campus)  
  – **Rentschler Library** (Hamilton campus)  
  – **Gardner-Harvey Library** (Middletown campus)  

• Your **first and last name**  
• Your **@miamioh.edu email address**  
• **Date** you’d like to book (e.g., “Dec 15,” “next Monday,” “11/12/2025”)  
• **Start time** and **end time** (e.g., “2 pm to 4 pm”) 
```

**Flags**: 📧 Email

#### ✅ Q8: tomorow

**Agents**: None

**Response**:
```
Hi there! It looks like you mentioned “tomorrow.” Could you let me know what you’d like to do for that day? For example:

• Check library hours  
• Book a study room  
• Search for materials  
• Ask a research question  

Just let me know, and I’ll be happy to help!
```

#### ✅ Q9: KL hours

**Agents**: None

**Response**:
```
I'm having trouble accessing our systems right now. Please visit https://www.lib.miamioh.edu/ or chat with a librarian at (513) 529-4141.
```

**Flags**: 🔗 URL | ⚠️ Error | 👋 Handoff

#### ✅ Q10: Art Lib

**Agents**: get_library_hours

**Response**:
```
Here are the hours for the **Wertz Art & Architecture Library** for the week of December 15–21, 2025:  
• **Monday (12/15):** 8 am – 5 pm  
• **Tuesday (12/16):** 8 am – 5 pm  
• **Wednesday (12/17):** 8 am – 5 pm  
• **Thursday (12/18):** 8 am – 5 pm  
• **Friday (12/19):** 8 am – 5 pm  
• **Saturday (12/20):** Closed  
• **Sunday (12/21):** Closed  

Need help booking a study room here or connecting with the Art & Architecture librarian? Just let me know!
```

**Flags**: ✅ Confirmation

#### ✅ Q11: subj lib

**Agents**: None

**Response**:
```
Sure—could you let me know which academic subject or department you’re interested in? For example, Biology, English, Business, etc. That way I can find the right subject librarian and guide for you.
```

#### ✅ Q12: WHAT ARE THE LIBRARY HOURS

**Agents**: libcal

**Response**:
```
Here are the King Library hours for the week of December 15–21, 2025 (Source: LibCal [VERIFIED API DATA]):

• **Monday (12/15)**: 8:00 am – 5:00 pm  
• **Tuesday (12/16)**: 8:00 am – 5:00 pm  
• **Wednesday (12/17)**: 8:00 am – 5:00 pm  
• **Thursday (12/18)**: 8:00 am – 5:00 pm  
• **Friday (12/19)**: 8:00 am – 5:00 pm  
• **Saturday (12/20)**: Closed  
• **Sunday (12/21)**: Closed

If you need hours for another week or branch, please let me know or visit our Ask-a-Librarian page: https://www.l
```

**Flags**: 🔗 URL

#### ✅ Q13: who is the biology librarian

**Agents**: None

**Response**:
```
I encountered an error. Please try again or contact a librarian.
```

**Flags**: ⚠️ Error

#### ✅ Q14: BoOk A rOoM

**Agents**: None

**Response**:
```
I encountered an error. Please try again or contact a librarian.
```

**Flags**: ⚠️ Error

## 🎯 Final Assessment

| Category | Quality Score |
|----------|---------------|
| Overall Success Rate | 86.3% |
| Subject Librarian Quality | 50.0% |
| Out-of-Scope Handling | 0.0% |
| Stress Test Resilience | 100.0% |

## 🚀 Production Readiness

### ⚠️ NEEDS IMPROVEMENT

Quality thresholds not met:
- ❌ Overall success rate: 86.3% (need ≥ 95%)
- ❌ Subject librarian quality: 50.0% (need ≥ 80%)
- ❌ Out-of-scope handling: 0.0% (need ≥ 80%)

## 💡 Recommendations

### Issues Found

**3_SUBJECT_LIBRARIANS**: 9 issues
- Psychology department librarian contact
- Who can help me with chemistry research?
- Business librarian email

**4_LIBGUIDE_SEARCHES**: 8 issues
- Research guide for biology
- Psychology research resources
- Business LibGuide

**5_POLICY_SERVICE**: 3 issues
- What is the library's guest policy?
- What cameras are available to borrow?
- What is the quiet study policy?

**6_PERSONAL_ACCOUNT**: 1 issues
- Renew my books online

**7_OUT_OF_SCOPE**: 6 issues
- When is course registration?
- Where can I eat on campus?
- Dining hall hours

**9_REGIONAL_CAMPUS**: 1 issues
- Who is the librarian at Rentschler Library?

**10_EDGE_CASES**: 5 issues
- hours
- libary hours
- KL hours

### Out-of-Scope Handling Issues

Found 22 queries that should be denied but weren't:

- What's the weather today?
- Will it rain tomorrow?
- How do I register for classes?
- When is course registration?
- Can you help me add a class?

### Next Steps

1. ❌ Fix identified issues before launch
2. 🔄 Re-run this test suite after fixes
3. 📊 Focus on failing categories
4. 🧪 Add more test coverage for edge cases

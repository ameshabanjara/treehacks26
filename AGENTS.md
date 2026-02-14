Poke - iMessage Planning Agent
Product: Conversational planning agent for iMessage group chats
Version: 1.0
 Last Updated: February 14, 2026

Overview
Poke is an AI agent that lives in iMessage group chats and handles group planning through natural conversation. Add Poke to any group chat, and it will facilitate the entire planning process from gathering preferences to booking reservations.
Core Value: Eliminates the "organizer burden" by having the AI handle logistics, scheduling, and decision-making coordination.

How It Works
Setup
Add Poke to an iMessage group chat (via contact sharing or invite link)
Poke introduces itself and explains how to activate planning mode
Planning Flow
User → "Hi Poke, help us plan for dinner"
  ↓
Poke → "Great! What times are people thinking?"
  ↓
Users → Drop their availability
  • "I'm free after 7pm"
  • "Saturday works for me"
  • "Anytime this weekend!"
  ↓
Poke → "What kind of food are we thinking?"
  ↓
Users → Give suggestions
  • "Italian sounds good"
  • "I'm craving Thai"
  • "Anything but pizza"
  ↓
Poke → Replies with curated list of 3-4 options
  • Rosa's Italian Kitchen - $$, 4.5⭐, available 7pm & 8pm
  • Thai Basil - $$, 4.3⭐, available 6:30pm & 8:30pm
  • Sushi Zen - $$$, 4.7⭐, available 8pm only
  ↓
Users → Majority vote
  • "Rosa's looks great!"
  • "I vote Rosa's"
  • "+1 for Rosa's"
  ↓
Poke → Creates reservation (browser-based booking)
  • Searches for reservation availability
  • Books via OpenTable/Resy/direct site
  ↓
Poke → Summarizes itinerary
  "✅ All set! Here's the plan:
   📍 Rosa's Italian Kitchen
   📅 Saturday, Feb 15
   ⏰ 7:00 PM
   👥 Party of 5
   📝 Reservation #12345
   
   See you there! 🍝"

Agent Capabilities
1. Conversational Planning Intent Detection
Monitors group chat for planning triggers
Activates when explicitly summoned ("Hi Poke...") or detects planning keywords
Maintains context across multi-turn conversations
2. Preference & Constraint Extraction
Extracts from conversation:
Time availability: "after 7pm," "this weekend," "Saturday"
Food preferences: cuisine types, dietary restrictions
Budget signals: "cheap eats," "somewhere nice," "not too expensive"
Location: "near downtown," "walking distance from campus"
Builds per-user preference memory across sessions
3. Multi-Source Venue Search
Uses Browserbase/Stagehand to browse Google, Yelp, and OpenTable directly (no external search APIs needed)
Stagehand's extract() pulls structured data: restaurant name, cuisine, price range, rating, review count, availability
Stagehand's act() navigates search filters: cuisine type, location, party size, date/time
Filters and ranks results by group constraints (cuisine preferences, budget signals, location, time availability)
Returns top 3-4 options optimized for the group
4. Decision Facilitation
Tracks responses and votes
Shows live tally ("3 votes for Rosa's, 1 for Thai Basil")
Prompts non-responders when needed
Declares decision when threshold reached (majority or unanimous)
5. Browser-Based Reservation
Uses Browserbase + Stagehand to automate the full booking flow:
Navigate to booking page (OpenTable, Resy, or restaurant's direct site)
Stagehand's act() fills in party size, date, and time
Stagehand's observe() verifies available slots before confirming
Browserbase Contexts persist login sessions so repeat bookings are faster
Browserbase stealth mode and captcha solving handle anti-bot protections
Falls back to providing a direct booking link if automation fails
6. Itinerary Summary
Generates final plan with all key details
Includes: venue, address, date, time, party size, confirmation number
Sends reminder day-before and day-of

Technical Stack

Core:

Poke (poke.com) -- The conversational agent platform, powered by Claude. Lives in iMessage group chats and handles all AI reasoning: intent detection, preference extraction, vote tracking, and decision facilitation. Poke connects to custom MCP servers via poke.com/settings/connections, calling tools to extend its capabilities.

Browserbase + Stagehand -- Cloud headless browser infrastructure for all web interactions. Stagehand is an AI browser automation framework built on Browserbase that provides four primitives:
  - act(): Execute actions on web pages using natural language (e.g., "click the 7pm reservation button")
  - extract(): Pull structured data from pages (e.g., restaurant name, rating, price, availability)
  - observe(): Discover available actions on any page
  - agent(): Automate entire multi-step workflows autonomously
Browserbase provides stealth mode, automatic captcha solving, residential proxies, and session persistence (Contexts) so login state on booking sites like OpenTable/Resy can be reused across sessions.

FastMCP Server (Render) -- The MCP server (src/server.py) is the glue layer between Poke and Browserbase. Deployed on Render, it exposes custom tools that Poke calls:
  - venue_search: Uses Browserbase/Stagehand to browse Google, Yelp, and OpenTable, extracting restaurant options that match the group's constraints
  - make_reservation: Uses Browserbase/Stagehand to navigate booking flows and complete reservations
  - check_availability: Uses Browserbase/Stagehand to verify open time slots before presenting options

Optional:

Claude Agent SDK -- Can be used inside MCP tools for multi-step LLM orchestration if needed. Not required for the MVP since Poke handles conversational reasoning and Stagehand handles AI-driven browser interaction. Useful for advanced scenarios like chaining multiple browser sessions or complex decision logic within a single tool call.

Architecture:

iMessage Group Chat
       ↕
Poke (poke.com, Claude-powered conversational agent)
       ↕
FastMCP Server (src/server.py, deployed on Render)
       ↕
Browserbase + Stagehand (cloud browser automation)
       ↕
Google / Yelp / OpenTable / Resy (venue search & booking sites)


Conversation Design Principles
1. Guided, Not Rigid
Poke asks clarifying questions in sequence but doesn't require strict command syntax. Natural language works.
✅ Good: "What times work for everyone?"
 ❌ Bad: "Please use format: YYYY-MM-DD HH:MM"
You should also be able to handle positive reactions, treat a like as an affirmative yes. 
2. Minimal Back-and-Forth
Gather preferences in 2-3 rounds max before presenting options. Don't interrogate.
3. Show, Don't Describe
Present options with actionable details, not paragraphs of description.
✅ "Rosa's Italian - $20 - 30, 4.5⭐, 7pm available"
 ❌ "Rosa's Italian Kitchen is a charming family-owned restaurant that specializes in..."
4. Facilitate, Don't Decide
Poke synthesizes and recommends but lets the group decide.
✅ "Rosa's has the most votes (3/5). Should I book it?"
 ❌ "I've booked Rosa's for you at 7pm."

Example Interaction
[User adds Poke to "Weekend Crew" group chat]

Poke: Hey everyone! 👋 I'm Poke, your planning assistant. Just say 
      "Hi Poke, help us plan for [activity]" and I'll take it from there!

---

Mike: Hi Poke, help us plan for dinner

Poke: Awesome! When are people thinking? This weekend? Weeknight?

Sarah: Saturday works for me
Mike: I'm free Saturday after 7
Lisa: Can do Saturday or Sunday
Alex: Saturday 👍
(or people all react a like to the message)

Poke: Great, Saturday it is! What kind of food are we feeling?

Sarah: I'm craving Italian
Mike: Italian works, or Thai
Lisa: Anything but sushi - just had it yesterday
Alex: Italian sounds good!

Poke: On it! Looking for Italian places for Saturday night... 🔍

      Here are some options:

      1️⃣ **Rosa's Italian Kitchen**
         📍 Downtown (0.5mi from campus)
         💰 $$ • ⭐ 4.5 (320 reviews)
         🕐 Available: 7:00pm, 8:00pm
         ✨ Known for: homemade pasta, cozy atmosphere

      2️⃣ **Bella Notte**
         📍 North End (2mi from campus)  
         💰 $$$ • ⭐ 4.7 (580 reviews)
         🕐 Available: 8:30pm only
         ✨ Known for: upscale, date night vibes

      3️⃣ **Lucia's Trattoria**
         📍 Westside (1.2mi from campus)
         💰 $$ • ⭐ 4.3 (210 reviews)
         🕐 Available: 6:30pm, 7:30pm, 9:00pm
         ✨ Known for: family-style, big portions

      Which one looks good? Just reply with the number or name!

Sarah: Rosa's looks perfect!
Mike: +1 Rosa's
Alex: Rosa's works
Lisa: Sure, Rosa's

Poke: Rosa's it is! 🎉 Let me grab that 7pm reservation... 

      [Checking availability...]
      
      ✅ **All booked!**
      
      📍 **Rosa's Italian Kitchen**
      🗓️ Saturday, February 15, 2026
      🕐 7:00 PM
      👥 Party of 4
      📞 (555) 123-4567
      🔗 Confirmation #R7234
      
      I'll remind everyone Saturday morning. Buon appetito! 🍝

---

[Saturday morning, 9am]

Poke: Good morning! Reminder: Dinner tonight at Rosa's at 7pm 
      (123 Main St). Who's still in?

[Everyone reacts with 👍]

Poke: Perfect! See you all there 😊

Future Capabilities (Roadmap)
Phase 2
Calendar integration: Auto-check availability from Google/Apple Calendar
Payment splitting: Coordinate Venmo/Splitwise for group expenses
Activity suggestions: Proactively suggest plans based on group history
Phase 3
Multi-day trip planning: Hotels, flights, itineraries
Recurring events: "Same place next week?"
Budget tracking: Monitor group spending across events
Phase 4
Cross-platform: WhatsApp, Instagram DMs, Slack
Smart scheduling: Learn group patterns, suggest optimal times
Venue partnerships: Exclusive deals for Poke-booked groups

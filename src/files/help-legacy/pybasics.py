"""
Welcome to Python Programming!
This file will show you some basic programming concepts.

You can open the console and test these examples.
Feel free to make changes and have fun!
"""

# These lines are called "comments".
# They are only meant for humans to read, since the computer ignores them.
# Sometimes they help us understand what the code is doing.
# When the computer sees a '#' on a line, it ignores everything coming after it.

"""
Here is another way to do comments, especially if you have more than one line
that you want to write.  Maybe you want to put a poem into your code, like this:

There once was a coder named Tim
Who wrote Python code on a whim
His comments were bright
Like a torch in the night
But his code was remarkably dim.
"""


# Okay, let's start with printing some text in the console.
# The 'print' function tells the computer to display something.

print("Hello, world!")  # This will print: Hello, world!

# Inside the ( ) are what we call 'arguments' or 'parameters'.
# In this example, they tell the 'print' function what to print.
# See? You CAN get into arguments without causing any trouble.
# Let's try a different argument this time:

print("This Python stuff is great!")  # Any guesses what this will print?


""" -------------- PYTHON BEING PICKY -------------- """
# It might be good to point out that Python can be picky. Very, very picky.
# If you misssspell a wurd, or Accidentally Put cApital letters where they
# weren't supposed to be, Python will be unhappy.
# I don't know whether you know much about pythons, but you DON'T want to
# make them unhappy.

# So, for example, these print statements WILL NOT WORK:
Print("Please?")   # <-- Nope, Python is unhappy, even if you say please.
PRINT("DO IT NOW!!")  # <-- Still unhappy, and shouting doesn't help.
prent("Sorry, I nead a spelcheker")  # <-- Apology NOT accepted.

# If your program doesn't work, check the log file for errors, and check
# your code for misspelled words, or missing quotation marks, parentheses, etc.


""" -------------- VARIABLES -------------- """
#
# Variables are like little boxes that hold information.
# Let's create a variable called 'age' and set it to 10.

age = 10  # We are setting age to 10.
print("I am", age, "years old.")  # This will print: I am 10 years old.

"""
Variables can be named just about anything you want, but there are a few rules:

VARIABLE NAMING RULES
	1: No spaces in a variable name! Use an underscore instead.
		my age = 97		<-- Doesn't work.
		my_age = 97		<-- Yep, good job!
		
	2: The variable name can't start with a number.
		3d_person = 0     <-- Oops!!  Starts with a number.
		person_3d = 0     <-- Ahh...  Much better.
	
	3: Only letters, numbers, and underscores can be used in the name.
		fun_n@me = 14     <-- Sorry!  That won't work.
		fun_name = 14     <-- Good fix.
		
	4: You can't use names that Python already uses for something else.
		Words like 'for', 'while', 'import', and 'if' are special words.
		They are usually called reserved words.  You can't have a
		variable named 'while', but you CAN have a variable named 'while3'.
		

Here are also some recommendations for how to name variables:

VARIABLE NAMING RECOMMENDATIONS
	1: Use lowercase, with underscores for spaces.
		somepeopleliketojamwordstogether = 45     <-- Ughh... Not easy to read
		other_people_use_underscores = 45         <-- So much nicer!

	2: Choose names that match what the variable is meant to do.
		foo123 = 37	    	<--  Huh?!  What's this for?
		player_points = 37		<--  Oh, that makes more sense.

"""


# You can use variables to do math, like this:

print("In 150 years, I will be", age + 150, "years old.")


# Data Types  (data just means information)
# Variables can hold different types of information (data), like numbers and text.
# We usually call text information a "string", because it's like a string of
# candy beads, where each candy is one letter or number.  Delicious!

name = "Alice"  # This is a string (text).
print("My name is", name)  # Prints: My name is Alice

# At another time, we'll learn how to slice that string into just the pieces
# of candy, I mean letters, that we want.  Super fun!


""" -------------- MATH -------------- """
# Basic Math Operations
# You can use Python to do math.
# Say goodbye to your calculator!

a = 5
b = 3
print(a + b)  # Addition
print(a - b)  # Subtraction
print(a * b)  # Multiplication
print(a / b)  # Division
# ...and there are other very mathy things you can do, but this is a good start.

# If you're using the console, you can also type in math problems more directly:
#  5 + 4 + 2 * 7
# But I think it's more fun* to use variables.
#
# * by 'fun', I mean harder.


""" -------------- DECISIONS -------------- """
# If Statements
# If statements let the computer make decisions.
# How much do you really trust your computer?

candy_cost = 10
my_money = 7
if candy_cost > my_money:
	print("Oh no, I don't have enough money to buy this important candy!")
elif candy_cost == my_money:    # <-- The == operator means "check if it's equal"
	print("Whew, just enough money!")
else:        # The only way we reach this next section is if my_money > candy_cost.
	print("Please take my money and give me the candy!")

# In this example, we're asking the computer to check whether the number stored in
#  candy_cost is greater than the number stored in my_money.  If that is True,
#  then it does the section of commands that are directly below it, which prints
#  out the sad, sad message.
#
# Otherwise, it checks the next part of the if statement.  The 'elif' part is short
#  for "else if", which it only checks if the last if statement was not True.
#
# If all the other if statements are not True, we finally get to the 'else' section.


""" -------------- INDENTATION -------------- """
# You probably noticed that the 'print' commands for the If statements are
# shifted in a little ways.  This is called indentation, and it's very important
# in Python.  It helps the computer know where the code sections start and stop.
# You will see this for decisions, loops, functions, and more.
#
# Always use the TAB key to indent your code sections.  Remember, Python is picky!


""" -------------- LOOPS -------------- """
# Loops let you repeat code without have to type it all in 250 times in a row.
# Here are some important kinds of loops:

# For Loop
# A For loop is used when you know how many times you want the loop to run.
# Let's do a for loop with numbers from 2 to 13.

for i in range(2, 14):   # range doesn't include the last number
	print("Please, kind sir, may I have", i, "candy bars?")


# While Loop
# A While loop is used when you DON'T know how many times you want the loop to run.
# This is really useful when waiting for something to happen.  If you have been a
# passenger on a long road trip, you might have tried something like this:

time_left = 9   # Just pretend that we don't know what number is in time_left.
while time_left > 0:   # This keeps going until "time_left > 0" is no longer true.
	print("Are we there yet?")
	time_left = time_left - 1


""" -------------- FUNCTIONS -------------- """
# Functions are pieces of code that you can reuse.
# You can change the way some functions work by passing in different arguments.
# This is a really important and useful concept!

# Let's 'def'ine a new function:
def greetz(name):    # <-- When a value gets passed in, it goes into 'name'
	print("Hello,", name)   # Now we can use the name variable in this function.

greetz("Bob")  # Calls the function and prints: Hello, Bob
greetz("Jenny")  # Same function, but this time it prints: Hello, Jenny


# Let's try making a function with a loop inside!
def lotsa_greetz(name, count):   # <-- This one has 2 parameters! (arguments)
	while count > 0:		  # <-- Keep looping while this is True
		print("Hello,", name)   # Whoa! A second layer of indentation!
		count = count - 1

lotsa_greetz("Bob", 25)  # Calls with 2 arguments and prints "Hello, Bob" 25 times.
lotsa_greetz("Jenny", 3)  # Same function, but prints: "Hello, Jenny" 3 times.


""" -------------- ADVANCED DATA TYPES -------------- """

# Lists
# A list is a collection of items that stays in a certain order.
# Lists can hold all kinds of data types, even other lists!
# Lists are defined with square brackets.

# Here's an empty list, which we can add to:
yoohoo = []   # Wow, that is very empty.
yoohoo.append('testing')  # <-- "Append" adds to the end of the list
yoohoo.append('yep!')
# Here's what that list would look like now: ['testing', 'yep!']

# You can also write out the list by hand, like this:
shopping_list = ["tomato", "potato", "alfredo"]

# You can read items from a list by their position in the list.
# The first item in a list is at position 0.

print("First item:", shopping_list[0])  # Prints: tomato

# You can also use a for loop to go through the whole list.
# In this next example, the variable 'to_buy' gets loaded with whichever
# item in the list is next.  Every time through the loop, it will
# be something different.

for to_buy in shopping_list:
	print("I need", to_buy)


# Dictionaries
# Dictionaries store data in named pairs.
# It's like a collection of variables that we can pass around.
# Dictionaries are defined with curly braces, but we use square
#  brackets to tell the dictionary what entry we're talking about.

# Here's an empty dictionary, which we can add to:
fruit_colors = {}  # I checked, and it's empty
fruit_colors['apple'] = 'red'   # <-- Notice the square brackets
fruit_colors['banana'] = 'yellow'
fruit_colors['cherry'] = 'red'

# Of course, we could also write the dictionary out by hand, like this:
fruit_colors = {"apple": "red", "banana": "yellow", "cherry": "red"}

# You can read from a dictionary by using the name of the entry, called the 'key'.
print("The color of an apple is", fruit_colors["apple"])


# Hopefully you have had fun learning some basic Python programming concepts!
# Be sure to check out the examples and try things in the console.
# Keep practicing, and don't forget to ask questions!

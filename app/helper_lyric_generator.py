

def phonetic_clean(word: str):
    """
    This function formats the output phonetic by erasing the characters:
    , "]", ",", "-", " ", ";" from the output
    """

    initial_length = len(word)
    modified_word = word
    counter = 0

    while (counter < initial_length):
        current = modified_word[counter:counter + 1]
        if (current == "[" or current == "]" or current == " " or
                current == "," or current == "-" or current == ";"):
            modified_word = modified_word[:counter] + modified_word[counter + 1:]
            counter -= 1

        counter += 1
    return modified_word
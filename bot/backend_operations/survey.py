
class SurveyManager:
    """
    Class to organize a survey by using multiple Telegram Polls. Its general work is similar to a linked list, with its internal state changing \
        focus from a set o one question / multiple options to the next when the user call a specific function

    Params:
        questions (list of dictionaries): Contains all questions that are part of a Telegram Survey. Its internal structure mimics the YAML file which contains the Spotify survey ('spotify_survey.yaml'): a list of dictionaries, each with 3 keys: 'text', the text to be displayed on a poll, 'options_set', the set of options to use (as desbride on the other parameter 'options'), and 'attribute', the attribute for which we are colleting info for (will be used to store poll resuslt on a database)

            Example: [{'text': 'Acousticness Interval', options_set: 'set1', 'attribute': 'acousticness'}, {...}, ...]

        options (complex dicts): Contains all set of options that go with a specific question. Its internal structure mimics the YAML file which contains the Spotify survey ('spotify_survey.yaml'): a dictionary where keys are the name of the set of options and values, a list of dictionaries where each represent a possible choice for a poll. Each of these dictionaries contains a key 'text' representing the option text to be displayed on Telegram Poll and some other keys representing the value to be read internally when this option is selected.

            Example: {'set1': [{text: 'Ignore interval', min_val: 0, max_val: 100}, {text: 'Low (0 - 25)', min_val: 0, max_val: 25}], 'set2' : {...}}

        Obs: Both questions and options will be presented and traversed on order of the main list (level 1 list)

    """

    def __init__(self, questions, options):
        self.questions = questions
        self.options = options

        # Store list of attributes that will be registered when running survey
        # ! Note: The order of this list shall follow  the same order as in the questions parameter
        self.attributes = []
        for _, attribute in enumerate(question['attribute'] for question in questions):
            self.attributes.append(attribute)

        if len(questions) == 0:
            raise ValueError('At least one question is required')
        if len(options) == 0:
            raise ValueError('At least one set of options is required')

        # ! Important: This member variable indicates the current state of the whole object
        # ! (indicates in which question of the survey the user is on)
        self.current_index = 0

    def get_poll_info(self):
        """
        Get the question and its options of the current step of the survey

        Returns:
            tuple(string, list), where 'string' is the question to be asked on the next poll and 'list' is a list of string with the corresponding options that can be select by the user

        """

        if self.current_index >= len(self.questions):
            return (None, None)

        question_text = self.questions[self.current_index]['text']
        options_set_name = self.questions[self.current_index]['options_set']

        options_text_list = []
        for _, text in enumerate(option['text'] for option in self.options[options_set_name]):
            options_text_list.append(text)

        return (question_text, options_text_list)

    def is_end(self):
        """
        Check if the current state (current question selected) is the last one

        Returns:
            True if current state is the lats, False otherwise

        """
        return self.current_index == len(self.questions) - 1

    def go_next_poll(self, number_of_skips=0):
        """
        Go to the next state of the survey (internal pointers to the next question). Can be set to jump a number of questions

        Args:
            number_of_skips(int): Number of questions to skip

        """
        self.current_index += (1 + number_of_skips)

    def get_skip_count(self):
        """
        If the current question dict has an attribute specifying the number of questions to be skiped if an answer was selected (key 'skip_if_set'), return this number. If a key with this name doesn't exist, return 0

        Returns:
            Number of questions (from the current question) to skip
        """
        return self.questions[self.current_index].get('skip_if_set', 0)



    def get_curr_attribute_values(self, user_selected_field=None):
        """
        Get which attribute the current poll referes to and, given which option the user select, what values are associated with this option

        Args:
            user_selected_field (int): An integer representing which option of the current poll was chosen by the user.

        Returns:
            Tuple (string, dict), where the first field is what attribute this poll is refering to and the second, a dict containing
                values associated with this particular answer (for example, if user selected an option called 'Very long (6 min +), this value would
                be {min_val: 360})

        """

        # Attribute associated with current poll
        curr_attribute_name = self.attributes[self.current_index]

        if user_selected_field is None:
            return (curr_attribute_name, None)

        # Get which set of options this current poll uses (string, not dictionary itself)
        curr_options_set_name = self.questions[self.current_index]['options_set']

        # Checking if the argument 'user_selected_field' is within the boundaries of selectable options
        if user_selected_field < 0 or user_selected_field >= len(self.options[curr_options_set_name]):
            raise ValueError('Invalid selection field')

        # Get the dict related to the user's selected option
        selected_option = self.options[curr_options_set_name][user_selected_field]

        # Get above dict, with the selected text the key 'text' (for showing to user at another time)
        selected_option_no_text = { key:selected_option[key] for key in selected_option}

        return (curr_attribute_name, selected_option_no_text)


    def reset_survey(self):
        """ Reset the SurveyManager object to the first question of the survey """

        self.current_index = 0



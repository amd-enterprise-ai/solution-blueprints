# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
from mri_ui import create_interface

if __name__ == "__main__":
    # Create and launch the interface
    interface = create_interface()
    interface.launch(server_name="0.0.0.0", server_port=7861, share=True, debug=True)

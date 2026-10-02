import React from "react";
import { Slider, SliderProps } from "@mui/material";
import { styled } from "@mui/material/styles";

const StyledSlider = styled(Slider)(({ theme }) => ({
    [theme.breakpoints.down("md")]: {
        pointerEvents: "none",
        "& .MuiSlider-thumb": {
            pointerEvents: "all",
        },
    },
}));

/**
 * A slider component that prevents accidental changes on mobile
 * by only allowing interaction with the thumb, not the track.
 */
const MobileSafeSlider: React.FC<SliderProps> = (props) => {
    return <StyledSlider {...props} />;
};

export default MobileSafeSlider;

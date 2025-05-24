import React from "react";
import { Slider, SliderProps, useMediaQuery, useTheme } from "@mui/material";
import { styled } from "@mui/material/styles";

const isMobileDevice = () => {
    const theme = useTheme();
    return useMediaQuery(theme.breakpoints.down("md"));
};

const StyledSlider = styled(Slider)(() => {
    if (isMobileDevice()) {
        return {
            "&.MuiSlider-root": {
                pointerEvents: "none",
            },
            "& .MuiSlider-thumb": {
                pointerEvents: "all",
            },
        };
    }
    return {};
});

/**
 * A slider component that prevents accidental changes on mobile
 * by only allowing interaction with the thumb, not the track.
 */
const MobileSafeSlider: React.FC<SliderProps> = (props) => {
    return <StyledSlider {...props} />;
};

export default MobileSafeSlider;
